# OR Prep

> **Scope.** This is a proof-of-concept procedural cognitive prep tool for urology residents, built as a research artifact. A resident inputs a case they are preparing for, and the tool produces a structured 5–20 minute briefing grounded in faculty-reviewed sources, with every claim cited. KU urology residents serve as opt-in beta testers. Deliverables are the system, the design rationale, and beta-use data suitable for publication. This is not a production service and is not clinical decision support.

If you are starting a Claude Code session against this repo, read [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md) first.

## What this tool does

The user is a urology resident preparing for a case in the next 12–24 hours. They open the tool, pick the case type from a constrained list, fill in patient factors (5–8 structured fields), optionally name the surgeon and the thing they're worried about, choose a time budget (5 / 10 / 20 minutes), and submit. The tool produces a structured briefing covering case summary, anatomy refresher, key decision points, anticipated complications, surgeon-specific divergences from the generic approach (if applicable), likely attending questions, and a sources list. Every factual claim is cited to a reviewed wiki page; every cite is hoverable to the source span.

The whole interaction is meant to take under the time budget the resident specified. Input under 60 seconds; read in 5 / 10 / 20 minutes; close the tab.

## What this tool does not do

Not a tutor. Not a question bank. Not a study tool. Not intraoperative guidance. Not clinical decision support. Not a generalized medical reasoning system. Not for patient-specific use beyond depersonalized case characteristics; no PHI.

## Stack

| Layer | Choice |
|-------|--------|
| Backend | Django 5.2 + Django REST Framework + psycopg 3 + `django-simple-history` |
| Frontend | Vite + React + TypeScript + React Router v7 |
| Database | PostgreSQL (via docker-compose); sqlite fallback for native dev |
| Auth | JWT bearer via `djangorestframework-simplejwt`; resident as the primary role |
| LLM | Anthropic Claude Sonnet (briefings) — Opus reserved for ingest if quality demands |
| Retrieval | None. Topic-scoped: a briefing loads the relevant module + surgeon-preference data into context. No vector store, no embeddings. |
| Audit log | `django-simple-history` on every model |
| Container | Docker / docker-compose dev stack |
| Deploy target | Single VPS + Docker Compose + Caddy/nginx + Let's Encrypt + daily Postgres dump |

## Current state

Standing today:
- Django scaffold with split settings (`config/settings/{base,dev,prod}.py`); compose with Postgres + backend + frontend; `/api/health/` endpoint returning DB-backed status.
- JWT auth: custom `User` model (email login, role enum), register/login/refresh/logout/me endpoints, `IsResident`/`IsFaculty`/`IsAdmin` permission classes.
- Frontend auth flow: login/register pages, protected `/`, `AuthContext` with transparent refresh-on-401.
- Briefing knowledge model (Phase A foundation):
  - `apps.cases.CaseTemplate` and `apps.cases.SurgeonPreference` — the briefing skeleton and per-attending divergence schema.
  - `apps.wiki.WikiPage` (now attached to a `CaseTemplate` or a legacy `Module`) and `apps.wiki.Claim` — one row per factual statement, with FK to `Document`, source quote/locator, and an audit-status lifecycle (`proposed → audited_ok / audited_weak → published / rejected`).
  - `apps.documents.Document` extended with `source_date`, `citation`, `review_status`, `reviewed_by`, `last_reviewed_at`.
  - `django-simple-history` on every model; citations are version-pinned at briefing time via the page's `history_id`.
- Ingest CLI: `manage.py ingest_document <path> --case-type ... --wiki-page-path ... --citation ... --source-date ... --uploaded-by ...` runs extract → propose claims → adversarial audit → compose markdown prose into `WikiPage.content` → persist draft Claims + an immutable `IngestRun` log row. Anthropic SDK calls are gated on `ANTHROPIC_API_KEY`. Content shape follows the Karpathy LLM-wiki model ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)): LLM writes the page, humans curate and review.
- Briefing CLI: `manage.py generate_briefing --case ... --factors ... --surgeon ... --time {5,10,20} --focus ...` runs a tool-use loop where the LLM must call `cite(claim_id)` for every factual claim; the server validates each call against published Claims and drops/flags unsupported ones before rendering markdown.
- Legacy curriculum schema retained for compatibility: `Module`, `LearningObjective`, `KnowledgeCheck`, `Reference` in `apps.modules`, and the `import_modules` YAML importer. The briefing path does not read these.

## Roadmap

Four phases with definitions of done in [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md). Items are marked done only when they actually land.

**Short status as of today:**
- Backend correctness layer + CLIs are built and tested up to the LLM call (Phase A foundation).
- The resident-facing UI is still just login / register / placeholder home. **No briefing input form, no renderer, no telemetry.** That's all Phase B and none of it has shipped.
- To produce a real briefing right now, you'd author content in Django admin and run the CLI; the web UI doesn't expose any of this yet.

### Phase A — Correctness layer + knowledge base extension (foundation built; awaiting real content)

**Schema and data layer — done.**
- [x] `apps.cases.CaseTemplate` + `apps.cases.SurgeonPreference` with `HistoricalRecords` and per-CaseTemplate provider/model override fields.
- [x] `apps.wiki.Claim` with FK to `Document` + source quote/locator + audit-status lifecycle (proposed → audited_ok / audited_weak → published / rejected).
- [x] `apps.wiki.WikiPage` attached to a `CaseTemplate` or legacy `Module` (XOR check constraint); page-level draft/published/archived status; `django-simple-history` version pinning at citation time.
- [x] `apps.wiki.IngestRun` — append-only log per `ingest_document` call (source, models, tokens, cost, verdict counts, status).
- [x] `apps.documents.Document` extended with source_date, citation, review_status, reviewed_by, last_reviewed_at.
- [x] Django admin registrations for all of the above.

**Pipelines (CLIs) — single-source path done; multi-source synthesis is a known gap.**
- [x] Ingest CLI (`manage.py ingest_document`): extract → propose claims → adversarial audit → compose markdown prose into `WikiPage.content` → persist draft Claims + IngestRun log row. Three LLM passes. Works correctly for **one source per wiki page**.
- [ ] **Multi-source synthesis (Karpathy LLM-wiki goal — not yet implemented).** Re-ingesting a second source onto the same wiki page currently rewrites the prose (without the LLM seeing the prior synthesis) and risks silent claim-ID collisions. The right shape is: ingest takes (current page state + existing claims + new source) and emits an updated synthesized page. Real refactor of `services/ingest.py` + the three system prompts. Blocks loading the full HoLEP source set (guideline + technique papers + atlas) into one coherent page. Rationale + design constraints in [docs/journal.md (2026-05-28)](docs/journal.md). Does **not** block the B1 hard-gate test or B2 — those proceed against a single-source wiki page.
- [x] Briefing CLI (`manage.py generate_briefing`): tool-use loop with server-validated `cite(claim_id)`; renders markdown with citations + a "Citation issues" footer for unsupported cites; loud warning when the model never called the cite tool.

**Provider abstraction — done (goes beyond original Phase A scope; landed because you asked).**
- [x] Provider ABC (`apps.wiki.services.providers`) supporting `anthropic`, `openai`, `lmstudio`, `openrouter`.
- [x] Per-stage routing (`LLM_BRIEFING_PROVIDER`, `LLM_INGEST_PROPOSE_PROVIDER`, `LLM_INGEST_AUDIT_PROVIDER`, `LLM_INGEST_COMPOSE_PROVIDER`) so different stages can use different backends.
- [x] Per-`CaseTemplate` override for the briefing stage (admin-editable).
- [x] Anthropic prompt caching on system prompt + static-catalog content blocks; cache-hit tokens flow into cost estimate.
- [x] OpenRouter cost-from-response (authoritative `usage.cost` instead of local pricing estimate).
- [x] Admin-editable LLM settings: per-stage provider+model + Fernet-encrypted API keys at `/admin/wiki/llmsettings/`. Singleton, write-only key fields, env vars as fallback.
- [x] Admin index cleanup: legacy `apps.modules` admin and `auth.Group` / JWT-blacklist clutter unregistered; AppConfig verbose names tightened to four clean sections (Case authoring, Knowledge base, Source documents, Users).

**Phase A close — TODO. Mostly content + config work, not code:**
- [ ] **Configure LLM provider + API key.** Either in Django admin at `/admin/wiki/llmsettings/` (encrypted at rest; recommended for non-engineers) or as env vars in `backend/.env`. The default is Anthropic Sonnet 4.6 for everything; per-stage overrides let you mix backends (e.g. local LM Studio for ingest propose, Anthropic Opus for audit).
- [ ] **Author the real HoLEP `CaseTemplate` in Django admin** at `/admin/cases/casetemplate/`: case_type, title, summary, anatomy_focus, decision_points, complication_patterns, attending_question_categories, patient_factor_fields. There's a placeholder smoke-test row at id=1 you can either edit or delete.
- [ ] **Bump your superuser role to `faculty`** at `/admin/users/user/` (created earlier via `createsuperuser`; default role is `resident`). Add a `SurgeonPreference` row attached to the HoLEP CaseTemplate.
- [ ] **Ingest one reviewed source PDF** (AUA HoLEP guideline preferred; any reviewed source works for the first pass). Review the proposed Claims at `/admin/wiki/claim/` and set `audit_status=published` on the ones that pass.
- [ ] **Run `generate_briefing` end-to-end** and confirm citations resolve, audit-flagged claims are excluded, no factual sentence is uncited.

### Phase B — Briefing surface (refined spec; not started; ordered)

Phase B turns the auth shell into a real briefing tool. **Full refined spec, performance targets, non-goals, and step-B1 implementation plan are in [docs/resident-ux-refinement.md](docs/resident-ux-refinement.md).**

Five ordered steps with hard gates between them. **Do not start step N+1 until step N is working end-to-end and Don has tested it.**

#### Step B1 — Per-case input schema mechanism (architectural foundation; awaiting Don's end-to-end test)

- [x] Rename `CaseTemplate.patient_factor_fields` → `input_schema` with default `{"quick": [], "expanded": []}`; single migration (`cases/0003`).
- [x] YAML schema spec at `schemas/case_template.schema.yaml` documenting top-level fields + the `input_schema` block (per-field: `name`, `label`, `type` ∈ {`select`, `text`, `number`, `boolean`, `multi_select`}, `required`, `options[]`, `help_text`). Includes field-name-as-contract + per-template-version invariants.
- [x] `manage.py import_case_templates` mirroring `import_modules.py`; validates structure (slug, type allowlist, non-empty options for select/multi_select, unique names across quick+expanded); reports created/updated/unchanged; `--dry-run` + `--path` flags; non-zero exit on validation failure.
- [x] Sample HoLEP at `modules/cases/holep/case_template.yaml`: realistic anatomy / decisions / complications / questions, quick set (`prostate_volume_g`, `indication`, `anticoagulation`, `prior_interventions`), expanded (`qmax_ml_per_s`, `pvr_ml`, `notable_comorbidities`).
- [x] Admin fieldsets surface `input_schema`.
- [ ] **Hard gate: Don tests B1 end-to-end before B2 starts.** Run `manage.py import_case_templates`, then author a SurgeonPreference + ingest a real source PDF + run `generate_briefing --case holep ...` and confirm the resident-input dict flows into the briefing prompt with the expected keys.

#### Step B2 — Single-screen input form

- [ ] DRF endpoint `POST /api/briefings/` wrapping `generate_briefing`; `GET /api/case-templates/` driving the case dropdown.
- [ ] Replace placeholder Home with a single-screen form (**no multi-step wizard**): greeting *"Good morning, Dr. [name]. Quick prep for tomorrow's case?"*; attending dropdown (defaults to last-used; asterisk + tooltip for attendings with documented prefs; selectable even without prefs); case dropdown (searchable; "Other" fallback opens free text and logs the entry to a new table so Don sees what's missing); case date (defaults tomorrow); time radio (5 / 10 / 20 min); case-specific fields rendered from `input_schema.quick`; "More detail" expander for `input_schema.expanded`; focus free-text; Generate button.
- [ ] Value-statement banner for users with <5 prior briefings: *"Five minutes of prep, grounded in [attending]'s preferences and reviewed literature. Citations on every claim."* Hidden after 5.
- [ ] Performance targets: form interactive in **<5s** from app open; quick set completable in **30-60s**; briefing renders in **<15s**.
- [ ] **Hard gate: Don tests B2 before B3 starts.**

#### Step B3 — Decision-led briefing output

- [ ] Refactor `BRIEFING_SYSTEM_PROMPT` to the new section order: (1) Setup + positioning with case-specific variations folded in; (2) **Decision points (3-5) — the centerpiece**, each with the moment, the consideration, the attending's preferred approach + citation, and the alternative; (3) Steps folded into the decision points where relevant (not a separate flat list); (4) Equipment + consumables checklist at the end, screenshot-friendly; (5) Anticipated complications, case-specific; (6) Post-op care to discharge (brief, only if a pathway exists for the case type); (7) Likely attending questions (3-5).
- [ ] Briefing renderer with hoverable `[[claim_id]]` citation tooltips revealing source quote. No-tool-calls warning rendered as a banner (backend already emits the diagnostic).
- [ ] **Non-negotiable:** when no documented preferences exist for the selected attending, briefing leads with a visible banner: *"No documented preferences for [attending]. This briefing reflects a standard approach. Confirm specifics with your attending pre-op."*
- [ ] **Hard gate: Don tests B3 before B4 starts.**

#### Step B4 — Follow-up turn capability

- [ ] Single input below briefing: *"Ask a follow-up question about this case."* Up to 3 follow-up turns per case.
- [ ] System prompt enforces: stay within the loaded case context + knowledge base; do not generalize to other urology topics; if out-of-scope, say so plainly and suggest the wiki or attending.
- [ ] After 3 turns, input swaps to *"Done with this case — I'll ask how it went later"* + Close Session button.
- [ ] Telemetry per follow-up turn: `turn_id`, `request_id`, `content`, `cost`, `citations called`. (Establishes the minimum `apps.telemetry` scaffolding needed here; expanded in B5.)
- [ ] **Hard gate: Don tests B4 before B5 starts.**

#### Step B5 — Post-case debrief

- [ ] Prompt fires either at end-of-day (if the case was today) or on next app open after the case date passes. **Not immediately after the case.**
- [ ] Form: *"How did the [case type] go with [attending]?"* + matched-reality text + missing text + wrong text + usefulness 1-5 radio. Skip button always available; **skipping is logged as a separate event**.
- [ ] Storage: debrief table tied to the original `request_id`; all submission fields optional.
- [ ] Closes the full Phase B telemetry parent: every briefing request stored with full inputs / outputs / citations / cost / latency / debrief.
- [ ] **Hard gate: Don tests B5; Phase B done.**

#### Disclaimer + footer (lands in B2; carried through)

- [ ] First-visit modal + persistent short footer: *"Educational preparation only. Not intraoperative guidance. Verify clinically relevant details with your attending."*

#### Explicitly NOT in Phase B

Per refinement spec — see [docs/resident-ux-refinement.md](docs/resident-ux-refinement.md#what-not-to-build):

- Multi-step wizard / modal flow (one screen, all fields visible).
- Attending typeahead UI polish, animations, transitions.
- Notification systems beyond the in-app debrief prompt — no email, no push.
- Calendar integration.
- Sharing or export beyond the equipment checklist screenshot.
- Anything that turns this into a general tutor in the follow-up turns.

### Authoring polish (parallel track; not started; do not preempt B1–B5)

Friction reducers for getting attending content into the system. Out of the resident-experience flow and explicitly **after** B5 ships. Both items target `SurgeonPreference` (and possibly `CaseTemplate`) authoring.

- [ ] **LLM-interviewed `SurgeonPreference` authoring.** Faculty-facing chat surface where a frontier LLM (Opus / Sonnet — interview quality matters, local models won't do) walks the surgeon through the case template's `decision_points`, `complication_patterns`, and `attending_question_categories`. Proposes a structured `preferences` JSON; surgeon reviews + edits inline; commit writes the row. Faculty-gated. Optional: log the chat transcript in a sibling-of-`IngestRun` model for traceability. Rationale + design constraints captured in [docs/journal.md (2026-05-28)](docs/journal.md).
- [ ] **`surgeon_preferences.yaml` importer** mirroring `import_case_templates` for attendings who prefer text editors over chat. Same model, alternate ergonomics.

### Phase C — Beta and post-case debrief (not started)

- [ ] Minimal VPS deploy: Docker Compose + Caddy + Let's Encrypt + daily Postgres dump.
- [ ] Post-case debrief form (matched-reality / missing / wrong / 1–5 usefulness rating).
- [ ] Read-only admin telemetry dashboard: briefing counts, case-type distribution, citation validity rates, debrief feedback, daily/monthly cost.
- [ ] Recruit 3–5 KU urology residents and run first real briefings.

### Phase D — Writeup (not started)

- [ ] Chair demo.
- [ ] Methods + results draft.
- [ ] AUA Education and Research subsection abstract submitted.
- [ ] Paper draft (target: *Journal of Surgical Education*).

"When to break the plan" criteria live in [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md).

## What to do right now

Two tracks can run in parallel:

1. **Close Phase A** (your work, mostly): drop an API key in `backend/.env` *or* configure it in `/admin/wiki/llmsettings/`, author the HoLEP `CaseTemplate` in admin, bump your role to `faculty`, ingest a reviewed source PDF, review the audit verdicts, run `generate_briefing`. No further code changes needed for Phase A unless something breaks in real use.
2. **Start Phase B at Step B1** (next code chunk): the per-case input schema mechanism. Detailed plan in [docs/resident-ux-refinement.md](docs/resident-ux-refinement.md#step-b1--approved-implementation-plan). Single migration + YAML schema spec + `manage.py import_case_templates` + a fully authored HoLEP sample. After B1 lands and you've tested it end-to-end, the next session moves to B2 (single-screen input form). **No working ahead** — each step gates on the previous one passing.

Phase A's remaining work is content and config. It can run in the background while Phase B code work proceeds, step by step.

## Running it locally

You need Docker, or Python 3.13 + Node 20+ for the native path. The Phase A ingest and briefing CLIs route through a provider abstraction (`apps.wiki.services.providers`) that supports `anthropic`, `openai`, `lmstudio`, and `openrouter`. Default config uses Anthropic; set the matching API key in `backend/.env` (native) or `docker/.env` (compose). To swap any pipeline stage to a different backend, set the matching `LLM_*_PROVIDER` + `LLM_*_MODEL` env vars (see `backend/.env.example`). LM Studio runs locally on `http://localhost:1234/v1` by default and is treated as free; briefing tool-use on local models depends on whether the loaded model supports function calling.

### Docker (preferred)

```bash
cd docker
cp .env.example .env       # first time only
docker compose up --build
docker compose exec backend python manage.py migrate           # first boot only
docker compose exec backend python manage.py import_modules    # seed module content
docker compose exec backend python manage.py createsuperuser   # admin login
```

Open `http://127.0.0.1:5173/`.

`docker compose down -v` wipes the Postgres volume.

### Native

```bash
# terminal 1
cd backend && .venv/bin/python manage.py runserver 127.0.0.1:8000

# terminal 2
cd frontend && npm run dev
```

Without `DATABASE_URL` set, the backend falls back to sqlite at `backend/db.sqlite3`. Useful for quick iteration without bringing the full stack up.

## Repository layout

```
backend/                Django: apps.users (auth), apps.cases (CaseTemplate +
                        SurgeonPreference), apps.wiki (WikiPage + Claim),
                        apps.documents (raw uploads + source freshness),
                        apps.modules (legacy curriculum schema, not used by briefings)
frontend/               Vite + React + TS; auth flow + protected routes
docker/                 docker-compose, Dockerfiles, .env.example
modules/                Legacy faculty-authored curriculum YAML (imported into apps.modules)
schemas/                YAML schemas for module / catalog
docs/                   Project notes and journal
OR Procedural Case Prep.md      Authoritative scope and four-phase plan; read this first
```

## Deploy

$20–40/month VPS (Hetzner, DigitalOcean, Linode); Docker Compose with prod settings; Caddy with Let's Encrypt; daily Postgres dump to S3 or Backblaze B2; hostname under a domain Don already owns. No CI/CD beyond a manual deploy script.

## License

MIT. See [LICENSE](LICENSE).

## Research and beta

KU urology residents are the opt-in beta cohort during Phase C. IRB protocol or amendment required before the first briefing is generated for a real case. Authorship plan with the chair and any contributing attending. De-identified data releasable alongside the paper. Target venues: *Journal of Surgical Education* primary; AUA Education and Research subsection abstract; Endourology Society if the talk fits.

## Constraints to honor

- Single instance, single specialty (endourology first, broader urology only if author bandwidth exists).
- ~$100/month all-in budget.
- Telemetry first-class — captured before the first beta user touches the system.
- Correctness over features — a briefing that confidently asserts something incorrect is the worst possible failure mode, because residents use it to prepare for live surgery.
- No PHI in inputs.
- No tutor surfaces, no calibration tracking, no commit-before-reveal interactions — explicitly out of scope.
