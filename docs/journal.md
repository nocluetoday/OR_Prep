# Project Journal

Design decisions, blockers, and rationale. Each entry: date, what changed, why, and the next decision point.

## 2026-05-26 — Project initialization

Repo stood up with the goal stated in [`OR Procedural Case Prep.md`](../OR%20Procedural%20Case%20Prep.md): a procedural cognitive prep tool for KU urology residents that produces a structured 5–20 minute briefing from a small structured input, with every claim cited to a reviewed source.

**Stack chosen.** Django 5.2 + DRF + Postgres + Docker on the backend; Vite + React + TypeScript on the frontend; JWT auth via `djangorestframework-simplejwt`; `django-simple-history` for row-level audit on every model. The deployment target is a single VPS with Docker Compose + Caddy.

**Knowledge layer shape.** Three layers: raw uploaded sources (`apps.documents`), LLM-curated wiki pages with page-level review status (`apps.wiki`), and the schema/template content in `modules/` (loaded into `apps.modules` via the `import_modules` management command). The briefing generator reads the case template + relevant published wiki claims + surgeon preferences directly into the LLM context. No vector store, no embeddings — topic-scoped at request time.

**What's running today.** Auth flow (register / login / refresh / logout / me + role-permission classes); the four-app data model (`users`, `modules`, `documents`, `wiki`); the YAML importer with two starter urology modules (HoLEP/BPH and ethics-in-consent) seeded as placeholder content; the dev compose stack with Postgres + backend + frontend.

**Next decision point.** Phase A: how to model case templates and surgeon preferences against the current `Module` / `WikiPage` schema. Two shapes:

1. Extend `Module` with a `case_template` JSONField and add a `SurgeonPreference` model FK'd to `Module`.
2. Introduce a separate `CaseTemplate` model, keep `Module` as legacy, migrate the two starter modules into the new shape.

Option 2 is cleaner but adds migration work. Decision deferred until the first Phase A claim-attribution piece is being designed, because that constrains how the briefing-generation LLM prompt assembles its context.

**Open questions tracked against `OR Procedural Case Prep.md` Phase C blockers.** IRB protocol approval, authorship plan with the chair, beta cohort confirmation, domain name + DNS, Anthropic API spend-alert mechanism, attending-preferences consent process. None block Phase A start.

## 2026-05-26 — Phase A foundation landed

**Budget recalibrated to ~$100/month** (down from $1000/month). The scope doc's prior cost math left enough headroom that this stays comfortable for briefing usage at the projected beta volume; the binding constraint is now ingest cost (~$2–5 per document) — added an `INGEST_MONTHLY_BUDGET_USD=$30` env var and a guardrail note in `ingest_document` that will harden once Phase B telemetry persists per-ingest cost. The "Cost projections at observed Phase C usage exceed $300/month" break-this-plan trigger dropped to $80/month sustained.

**Schema decision: new `apps.cases`, not extension of `Module`.** Option 2 from the prior journal entry. `CaseTemplate` (one per case type, with structured anatomy_focus / decision_points / complication_patterns / attending_question_categories / patient_factor_fields) and `SurgeonPreference` (FK to CaseTemplate + surgeon User, JSON list of preference items each with own attribution). The starter `Module` rows (HoLEP/BPH, ethics-in-consent) are left in place; the briefing path no longer reads them. Faculty authoring of CaseTemplate / SurgeonPreference happens through Django admin in Phase A; a YAML importer mirroring `import_modules` lands only if author bandwidth justifies it.

**Claim model anchored to WikiPage.** `apps.wiki.Claim` carries `statement`, `source_quote`, `source_locator` (JSON), `audit_status` (proposed → audited_ok / audited_weak → published / rejected), `audit_notes`. WikiPage is now attached to either a `CaseTemplate` or a legacy `Module` (mutually exclusive, enforced by check constraint). Page version pinning rides on `django-simple-history`: the briefing's `cite()` tool resolves a claim_id, fetches the current page+claim history_id, and returns them in the validated citation payload. The PK pair (page_id, page_history_id) is what Phase B telemetry will persist per-citation.

**Source freshness on Document.** Added `source_date` (free-form YYYY-MM), `citation` (full human-readable string), `review_status` (unreviewed / published / archived), `reviewed_by`, `last_reviewed_at`. Document FK is mutually exclusive between `case_template` and `module`.

**Ingest pipeline (`manage.py ingest_document`).** Two-pass: extract text from PDF/TXT/MD → propose claims with `claude-sonnet-4-6` → adversarial audit each (claim, quote) pair with `claude-opus-4-7`. Verdicts map to `audited_ok` / `audited_weak`; nothing auto-publishes. Anthropic calls live in `apps.wiki.services.anthropic_client` and raise `AnthropicConfigurationError` when `ANTHROPIC_API_KEY` is unset.

**Briefing pipeline (`manage.py generate_briefing`).** Loads CaseTemplate + SurgeonPreference (filtered to the named surgeon if any) + all published Claims for the case. Single tool-use loop where the LLM must call `cite(claim_id)` for every factual statement; server validates each call against published claims and pins the citation to the WikiPage's current history_id. Failed cites are collected into a "Citation issues" footer rather than silently dropped, so faculty review of a briefing can catch any unsupported statements.

**Demonstrable artifact remaining for Phase A close.** A real reviewed source PDF (AUA HoLEP guideline preferred) ingested through `ingest_document`, plus the HoLEP `CaseTemplate` and Neff `SurgeonPreference` populated via admin, plus `generate_briefing --case holep ...` producing a structured cited briefing end-to-end. Don needs to drop the source PDF in to close out.

**Permissions tweak.** `.claude/settings.json` deny pattern `Read(./wiki/**)` over-matched `backend/apps/wiki/`. Narrowed to `Read(./wiki/*.md)` + `Read(./wiki/**/*.md)` so the runtime LLM-curated markdown stays denied while the Django wiki app source stays readable. Same scoping applied to `uploads/` and `media/`.

**Next decision point.** When ingesting the first real PDF: confirm whether the propose+audit token counts and verdict quality justify keeping Opus on the audit pass, or whether Sonnet 4.6 is sufficient. The audit pass is the expensive call; downgrading it would drop per-document ingest cost roughly 5x.

**Deferred for after the first real briefing run: Anthropic prompt caching.** The static parts of the briefing prompt (system prompt + the published-claims catalog for a case) are exactly what `cache_control: {type: "ephemeral"}` is for, and the scope doc's cost model assumed it. Skipping it now keeps Phase A small, but wire it in before opening the briefing CLI to real residents — at the $100/month budget it matters more than it would have at $1000/month.
