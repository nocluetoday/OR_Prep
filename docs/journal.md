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

## 2026-05-26 — LLM-wiki architecture reference + ingest pipeline alignment

**Reference model: Karpathy's LLM-wiki gist (`442a6bf555914893e9891c11519de94f`).** Adopting this as the explicit architectural source for the content layer. Key tenets from the gist that we follow:

- **No RAG.** The LLM reads an index/topic-scoped artifact directly, not retrieved fragments. Our briefing path already does this (CaseTemplate + SurgeonPreference + published Claims loaded in full per case; no embeddings, no similarity search).
- **The LLM writes the wiki, not humans.** Humans curate sources and review; the LLM produces the page content. Before today's change our `ingest_document` only persisted atomic Claims and left `WikiPage.content` empty. Now the ingest pipeline has a third compose pass: after propose + adversarial audit, the audit-OK claims feed a markdown-writing call that populates `WikiPage.content` with cited prose (each factual sentence ends with `[[claim_id]]`). Faculty reviews the prose + the underlying claims in admin before publishing.
- **Append a log entry.** Added `apps.wiki.IngestRun` — one immutable row per `ingest_document` invocation, recording source, pages touched, claim counts by audit verdict, per-pass token usage, total cost, models used, and status. Browsable in admin. Treated as the wiki's append-only operation log.

**Where we diverge from the Karpathy model (knowingly):**

- **Batch ingest, not interactive.** Karpathy's flow has the LLM discuss findings with the human mid-ingest. We have a fire-and-forget CLI today. Faculty review happens in admin after the run completes. Interactive ingest is a Phase B web-UI concern; CLI stays batch through Phase A.
- **One page per ingest.** Karpathy: one source touches 10–15 pages. We take one `--wiki-page-path` per run. Decomposition into multi-page touches is deferred until a real source PDF shows what shape this actually wants.
- **Atomic Claims alongside prose.** Karpathy's wiki is page-centric. We retain the `Claim` atom because the briefing's `cite(claim_id)` validated-tool-call contract requires server-side identity for each citation; the scope doc explicitly mandates this. Pages carry the prose; claims are the citation hooks.

**What this changes in code (commit to land after this entry):**

- New `apps.wiki.IngestRun` model + admin registration; migration `wiki/0003`.
- `apps.wiki.services.ingest.compose_page()` — third LLM pass turning audit-OK claims into markdown.
- `apps.wiki.services.ingest.IngestResult` carries `page_markdown` + `compose_tokens_in/out` + `compose_cost_usd`.
- `ingest_document` opens an `IngestRun` row up front, finalizes it on success or failure, and writes the composed prose into `WikiPage.content`. Pre-existing page prose is preserved as an HTML comment beneath the new content so the diff is reviewable in admin history.

**Cost-model recalc.** The compose pass is a third LLM call per ingest. Rough estimate against the scope doc's original numbers: propose ($0.05–0.15) + audit ($0.05–0.15, Opus heavier) + compose ($0.03–0.10, Sonnet on much smaller input). Order-of-magnitude $0.15–$0.40 per ingest, up from $0.10–$0.30. Still fits the $30/month ingest envelope at ~75 documents/month, which is well past expected authoring volume. Re-measure once real PDFs land.

**Next decision points for the ingest pipeline:**

- Chunking strategy when the first real PDF is too large for a single propose call. Probably section-aware chunking with overlap, but defer the design until a real PDF tells us what sections look like.
- OCR fallback for image-only PDFs. `pypdf` returns garbage; either add `pdfplumber + tesseract`, or use Anthropic's vision input on the PDF directly (probably the cleaner path).
- Whether the per-claim audit should be one batched call (cheap) or N independent calls (strict). Test both on the first real document; pick by verdict quality, not cost.
- The prior-content-as-HTML-comment behaviour in re-ingest is redundant with simple-history. Drop it once admin merge UX gets real use; keeping for now so faculty can eyeball the diff inline without flipping to history.

## 2026-05-26 — Provider abstraction (chunk 1)

**Motivation.** User wants local-model support via LM Studio, plus a clean path to OpenAI and OpenRouter. Lock-in to the Anthropic SDK in `apps.wiki.services.anthropic_client` would have made any of those a per-call branch; better to introduce a thin provider interface now while there are only two callers (ingest + briefing) to update.

**Shape.** New module `apps.wiki.services.providers/` with:

- `base.py` — provider-agnostic dataclasses (`Message`, `ToolSpec`, `ToolCall`, `ToolResult`, `CompletionResponse`, `Usage`) and the `Provider` ABC. Stop reasons normalized to four values: `end`, `tool_use`, `max_tokens`, `error`. `json_mode` is a hint applied only by providers that support `response_format`; Anthropic ignores it (prompt instructs JSON shape).
- `anthropic.py` — wraps `anthropic.Anthropic`. Native Claude pricing table for cost estimation. Translates Message ↔ Anthropic content blocks (text / tool_use / tool_result).
- `openai_compat.py` — one class for OpenAI, LM Studio, and OpenRouter. The three speak the same wire format; differences are `base_url`, the env var holding the API key (with a sentinel fallback for LM Studio), and pricing (OpenAI: local table; LM Studio: free; OpenRouter: not estimated locally because per-model pricing varies — the API returns actual cost in `usage`, which we don't surface yet).
- `registry.py` — `get_provider(kind)` dispatches to one of the four kinds; raises `ProviderConfigurationError` for unknown values.

**Settings.** Each pipeline stage has its own provider + model:

- `LLM_BRIEFING_PROVIDER` / `LLM_BRIEFING_MODEL`
- `LLM_INGEST_PROPOSE_PROVIDER` / `LLM_INGEST_PROPOSE_MODEL`
- `LLM_INGEST_AUDIT_PROVIDER` / `LLM_INGEST_AUDIT_MODEL`
- `LLM_INGEST_COMPOSE_PROVIDER` / `LLM_INGEST_COMPOSE_MODEL`

Defaults: all `anthropic`, Sonnet 4.6 everywhere except audit (Opus 4.7). The old `ANTHROPIC_BRIEFING_MODEL` / `ANTHROPIC_INGEST_MODEL` / `ANTHROPIC_AUDIT_MODEL` env vars are honored as defaults for the new `LLM_*_MODEL` values so existing `.env` files keep working with no change.

**Provider config:** `OPENAI_API_KEY` / `OPENAI_BASE_URL`; `LMSTUDIO_API_KEY` (defaults to the sentinel string `lm-studio`) / `LMSTUDIO_BASE_URL` (defaults to `http://localhost:1234/v1`); `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL`.

**Refactor.** `apps.wiki.services.ingest` and `apps.cases.services.briefing` no longer import an SDK directly. Each pass (propose, audit, compose) takes a `Provider` instance and calls `provider.complete(...)`. The briefing tool-use loop is now provider-agnostic — assistant turns carry `tool_calls`, user turns carry `tool_results`, each provider translates to its native wire format. Deleted `apps.wiki.services.anthropic_client` and its `AnthropicConfigurationError`; callers now catch `ProviderConfigurationError` from the providers package.

**Smoke-tested:** missing-key paths fire the correct `ProviderConfigurationError` for both ingest and briefing under the default anthropic provider; switching `LLM_BRIEFING_PROVIDER=lmstudio` with a bogus base URL produces a network connection error (the provider is actually instantiated and called — the abstraction works end-to-end). `IngestRun` rows capture the per-stage model names.

**Known trade-offs:**

- Briefing tool-use loops need providers that support function calling. Most local models loaded in LM Studio do not. If a user routes briefing to LM Studio with a non-tool-using model, the loop will exit with all factual statements going through the LLM's text content (no validated cites). The `rejected_cites` footer in the output will be empty (the model never tried to cite), but the briefing will still be unsupported. Document the gotcha; better diagnostic is deferred work.
- `response_format={"type": "json_object"}` is disabled when tools are in use because some backends reject the combo. Ingest passes don't use tools, so JSON mode applies there; briefing uses tools, so no JSON mode (briefing doesn't need it — outputs are markdown).
- **Model-name silent-stick when swapping providers.** Existing `.env` files with only `ANTHROPIC_BRIEFING_MODEL=claude-sonnet-4-6` set will keep that as the default for `LLM_BRIEFING_MODEL` even if `LLM_BRIEFING_PROVIDER` is swapped to e.g. `lmstudio`. LM Studio will then reject the model name. When swapping a stage's provider, always also set its `LLM_*_MODEL` env var to a model the new backend knows.

**Chunk 2 (deferred):**

- OpenRouter cost-from-response: parse `usage.cost` (when present) instead of returning 0.0 from the local pricing table.
- LM Studio tool-use probe: at startup, query the loaded model's capabilities and warn before routing briefing to it.
- Per-CaseTemplate provider override so high-stakes cases can pin Anthropic while exploratory cases can use cheap local models.
- Prompt caching for Anthropic (deferred from earlier; still relevant).
- Settings UI in admin so non-engineers can swap providers without editing env files.

## 2026-05-26 — Provider abstraction (chunk 2)

**Four chunk-2 deferred items landed; one deferred again.**

**1. Anthropic prompt caching.** `Message` gained a `cache: bool` field and `Provider.complete()` gained `cache_system: bool`. The AnthropicProvider applies `cache_control: {"type": "ephemeral"}` to the system block when `cache_system=True`, and to per-message content blocks when `Message.cache=True`. The converter now also merges consecutive same-role Messages into one Anthropic message with multiple content blocks — this is the mechanism that lets callers split a static-cacheable prefix from variable input across two Messages and have it emerge as one user message with one cached + one uncached text block. Cache-hit token counts (`cache_read_input_tokens`) flow into `Usage.cached_input_tokens` so the per-call cost estimate picks up the discount.

OpenAI-compat providers ignore both flags (no explicit cache API for chat completions; OpenAI does automatic caching server-side on long prompts).

Cache targets wired:
- **Ingest propose**: document_text user message + system. (Audit pass benefits — same text within 5 min hits cache.)
- **Ingest audit**: document_text split off into its own cacheable message, claims list in a separate uncached message. System cached.
- **Ingest compose**: system cached. (User content is variable per ingest; not worth caching.)
- **Briefing**: case_template + surgeon_preferences + available_claims (the static catalog that repeats across briefings on the same case) in one cacheable message; patient_factors + surgeon_email + time + focus in a separate uncached message. System cached. Each subsequent tool-loop turn rides on the same cached catalog.

Expected impact at the $100/month cap: briefing repeats on the same case within 5 minutes pay ~10% of input price on the catalog block (typically 80%+ of the briefing input). This is the difference between caching being a nice-to-have and a meaningful budget line.

**2. Per-CaseTemplate provider override.** `CaseTemplate.briefing_provider_override` and `CaseTemplate.briefing_model_override` (CharFields, blank-by-default). Briefing service uses them when set, else falls back to `LLM_BRIEFING_PROVIDER` + `LLM_BRIEFING_MODEL` settings. Surfaced in admin under a dedicated fieldset with help text explaining the fallback. Migration `cases/0002`. Verified by setting the override on a placeholder CaseTemplate and observing the briefing CLI route to the override provider.

**3. OpenRouter cost-from-response.** When `LLM_*_PROVIDER=openrouter`, the OpenAI-compat provider now sends `extra_body={"usage": {"include": True}}` on every request, then extracts `usage.cost` from the response into `Usage.actual_cost_usd`. Both providers' `estimate_cost_usd` short-circuit to the actual value when present, so OpenRouter spend is authoritative (not estimated from a local table that doesn't have most of their hundreds of models). Extraction tries three access paths (`.cost` attribute, `model_extra`, `model_dump`) to be robust across openai SDK versions.

**4. Briefing diagnostic for non-tool-using models.** When the loop exits with zero tool calls AND the case had publishable claims, the markdown output leads with a prominent warning block and the CLI prints a yellow WARNING to stderr. Saves a class of confusion where a local LM Studio model returns nice-looking text that's silently uncited.

**5. Deferred again to chunk 3: settings UI in admin** for non-engineer provider swapping. Reasoning: per-CaseTemplate override (which DID land) covers the most common case (Don wants HoLEP on Anthropic, other cases on local models). A global-settings admin model is a real refactor (Django settings aren't editable from admin without a custom backed model + middleware to re-resolve at request time) and out of scope for chunk 2.

**Smoke-tested:**
- Missing API key on default provider → clear ProviderConfigurationError.
- Per-case override routes through the override provider (verified by setting `briefing_provider_override=lmstudio` with bogus base URL — get a network error, not the Anthropic-key error).
- Cache-marker converter produces the canonical Anthropic content shape: one user message with two text blocks, cache_control on the static block only; tool_use round-trip preserved through subsequent turns.

**Known limitations carried forward:**

- LM Studio tool-use is still model-dependent. The new diagnostic makes it loud when a model fails to call `cite()`, but we still don't pre-probe before running. The diagnostic catches the failure mode after the fact, which is good enough for now.
- Prompt-caching cost estimate depends on the model being in the local Anthropic pricing table. For unknown models, cost falls back to 0; the actual money flowing is what the provider charges (Anthropic dashboard remains authoritative).
- **Cost shape of the new caching:** Anthropic charges ~1.25x normal input price for cache writes and ~0.1x for cache reads (5-min ephemeral). First call in any flow is a write; subsequent calls within the window are reads. Net win requires ≥2 calls in the window — which is exactly the ingest pipeline shape (propose then audit), and the briefing tool-use loop shape (turn 1 then turns 2..N). Single-call flows with tiny system prompts (e.g. compose-only on a small claim set) pay slightly more than no caching; acceptable rounding error.
- **OpenAI-compat cache accounting is provider-side only.** Our local pricing fallback for OpenAI / LM Studio / OpenRouter does not subtract `cached_input_tokens` because the OpenAI pricing struct has no cached-price column. OpenAI does automatic server-side caching on long prompts (their dashboard reflects it); OpenRouter folds the discount into `usage.cost` which we now surface authoritatively; LM Studio is free. Net: trust the dashboards / `usage.cost`, not the local estimate, for OpenAI-compat backends.

## 2026-05-27 — Admin-editable LLM settings + admin index cleanup

**Two paired asks: surface LLM config in the admin GUI (with secure key storage), and simplify the admin section, which had grown cluttered with legacy + framework noise.**

**LLMSettings singleton.** New row at `pk=1` in `apps.wiki.LLMSettings` carries per-stage provider + model (briefing, ingest_propose, ingest_audit, ingest_compose), encrypted API keys per provider (`anthropic_api_key_enc`, `openai_api_key_enc`, `openrouter_api_key_enc`, `lmstudio_api_key_enc`), and per-provider base URL overrides. Encryption is Fernet with a key derived from `DJANGO_SECRET_KEY` via SHA-256 + URL-safe base64. Stored ciphertext is a base64 string in a TextField; never logged, never displayed. `set_api_key(provider, plaintext)` encrypts; `get_api_key(provider)` decrypts (returns empty string on `InvalidToken`, treating a rotated SECRET_KEY as "key needs to be re-entered"). `simple_history` audits changes — the history table holds ciphertext only.

**Resolution precedence: DB > env > hardcoded fallback.** New `apps.wiki.services.llm_config` exposes `get_stage_provider(stage)`, `get_stage_model(stage)`, `get_api_key(provider)`, `get_base_url(provider)`. Providers and pipeline services route through these instead of reading `django.conf.settings` directly. An install with no `LLMSettings` row falls through to env vars exactly as before — no breaking change. Per-CaseTemplate override still takes precedence over the global LLMSettings + env for the briefing stage.

**Admin form is write-only for keys.** `LLMSettingsForm` uses `PasswordInput(render_value=False)` for each key with "leave blank to keep" help text; submitted plaintext is encrypted via `set_api_key()` before save. The ciphertext fields are `exclude`d from the form. Provider dropdowns offer the four kinds + a blank option ("use env LLM_*_PROVIDER"). The singleton UX: `changelist_view` redirects `/admin/wiki/llmsettings/` straight to the singleton's change page; `has_add_permission` returns False once the row exists; `has_delete_permission` always False. Faculty clicks "LLM settings" in the admin index, lands on the edit form, types values, saves. Done.

**Smoke-tested end-to-end:** with no DB row, the briefing CLI raises the new "Anthropic API key not configured. Set it in Django admin (LLM settings) or as ANTHROPIC_API_KEY in backend/.env" error. After `LLMSettings.set_api_key('anthropic', 'sk-test')` + save, the briefing reaches the Anthropic API and gets a real 401 for the fake key — proving the DB-stored encrypted key decrypts and flows through to the SDK correctly.

**Admin index cleanup.**

- Unregistered `apps.modules` admin entries (Module / LearningObjective / KnowledgeCheck / Reference). The README has called these legacy since the Phase A foundation; the admin clutter was misleading. Models stay in the DB; inspection is via shell.
- Unregistered `django.contrib.auth.Group`. Role-based permissions in `apps.users.permissions` cover what we need; group-based perms add a UI column without adding capability.
- Unregistered `rest_framework_simplejwt.token_blacklist.BlacklistedToken` and `OutstandingToken`. The JWT blacklist updates automatically on refresh-token rotation; nothing in admin is actionable.
- Removed `groups` and `user_permissions` from the `UserAdmin` fieldsets (the m2m fields are still on the model from `AbstractUser`, just hidden from the form).
- Tightened `AppConfig.verbose_name` for cases ("Case authoring"), wiki ("Knowledge base"), documents ("Source documents"), users ("Users") so the admin index reads as four clean section headers.

Post-cleanup admin index shows: Case authoring (CaseTemplates, SurgeonPreferences) / Source documents (Documents) / Users (Users) / Knowledge base (Claims, IngestRuns, LLM settings, WikiPages). Four sections, all of them actionable, no framework noise.

**Known limitations:**

- Rotating `DJANGO_SECRET_KEY` invalidates all stored API keys (Fernet decryption fails with `InvalidToken`, returning empty string, falling through to env). Faculty re-enters keys after a rotation. This is intentional — a separate `LLM_CONFIG_KEY` env var would let them rotate independently, but adds another secret to manage; the SECRET_KEY-derivation trade-off matches the PoC scope.
- The `_db_settings()` lookup in `llm_config.py` does one query per provider/stage resolution. For batch CLIs this is a handful of queries per ingest/briefing run — negligible. If a future hot-path needs it, `lru_cache` plus an explicit cache-bust on `LLMSettings.save()` would handle it.
- **History table grows with every save.** `simple_history` writes a `HistoricalLLMSettings` row on each save — including every dropdown change in admin and every key rotation. Ciphertext stays encrypted in those rows. Over years this could accumulate; not a problem in PoC. Periodic `manage.py clean_old_history` ([django-simple-history command](https://django-simple-history.readthedocs.io/en/latest/utils.html#clean-old-history)) handles trimming if it becomes one.

## 2026-05-27 — Phase B refinement spec + step B1 plan captured (execution deferred)

User refined the Phase B spec significantly: single-screen form (not multi-step), per-case input schema declared in YAML alongside template content, decision-led briefing output, follow-up turn capability scoped to one case, post-case debrief that fires at end-of-day or next-app-open (not immediately after the case). Five ordered steps with hard gates — no working ahead. Full spec + step-B1 implementation plan captured in [docs/resident-ux-refinement.md](resident-ux-refinement.md).

The README's Phase B section restructured into the five ordered chunks (B1-B5) with explicit hard-gate language and a "what not to build" callout pointing at the source spec.

**Execution deferred to a future session** to avoid usage overruns in this one. The first code chunk when work resumes is **B1: per-case input schema mechanism** — rename `CaseTemplate.patient_factor_fields` → `input_schema`, write the YAML schema spec, build `manage.py import_case_templates` mirroring `import_modules.py`, author the HoLEP sample at `modules/cases/holep/case_template.yaml`, single migration. Detailed plan + verification list lives in the refinement doc.

**Key invariants surfaced during planning, to capture when B1 actually ships:**

- **Field `name` is a contract.** Once a YAML field's `name` is published, changing it silently invalidates any future briefings whose persisted resident input was keyed to the old name. Migration story for renames belongs to step B5 (telemetry / debrief) when submitted inputs start being persisted.
- **Schema versioning is per-template, not per-schema.** If `input_schema`'s allowed types ever extend (e.g. adding `date`), there's no machine-readable signal that prior submissions used the old shape. Document the caveat inside `schemas/case_template.schema.yaml`.
- **Layout: flat under `modules/cases/<case_type>/case_template.yaml`** (not specialty-nested), because the PoC is single-specialty per the scope doc.

**Out of scope until B1 closes:** any frontend code, any briefing prompt / service changes, any telemetry-app scaffolding, a second case template. The refinement doc's "What not to build" section names additional non-goals across Phase B (no multi-step wizard, no notification systems beyond in-app, no calendar integration, no general-tutor follow-ups).

## 2026-05-27 — Step B1 landed (code-side; awaiting Don's end-to-end test)

All B1 code work landed against the [approved plan](resident-ux-refinement.md#step-b1--approved-implementation-plan):

- `CaseTemplate.patient_factor_fields → input_schema` rename via `cases/0003`. Module-level `_default_input_schema()` callable returns `{"quick": [], "expanded": []}` (not a lambda — migrations need it serializable). Migration is the expected `RemoveField` + `AddField` diff.
- `schemas/case_template.schema.yaml` documents the full YAML shape (top-level fields, `input_schema.quick` + `input_schema.expanded` blocks, per-field properties) and embeds the three invariants the refinement plan flagged: field-name-as-contract, per-template versioning, unique names across both groups.
- `apps.cases.management.commands.import_case_templates` mirrors `import_modules` (rglob, `_template` skip, atomic per-file upsert keyed on `case_type`, `--dry-run` + `--path` flags, created/updated/unchanged counters). Strict validation: slug shape on `case_type` and field `name`s; type allowlist (`select | text | number | boolean | multi_select`); non-empty `options` for select/multi_select; unique field names across `quick + expanded` in a single file. Validation failures exit non-zero with clear stderr.
- `modules/cases/holep/case_template.yaml` authored with realistic urology content (4 anatomy focus areas, 5 decision points, 5 complication patterns, 5 attending-question categories) plus the planned input schema (4 quick / 3 expanded). Flat layout under `modules/cases/<case_type>/` per the layout choice locked in the refinement doc.
- Admin fieldset surfaces `input_schema` (replaces the dead `patient_factor_fields` reference).

**Verification list (all 11 steps green):** `manage.py check` passes; migration applies cleanly; `--dry-run` parses without writes; first real import shows `updated: holep` (because the placeholder smoke-test row already had `case_type=holep` at pk=1 from earlier); re-run reports `unchanged: holep`; editing the YAML and re-running reports `updated`; duplicate-field-name negative test exits 1 with the right message; empty-options negative test exits 1 with the right message; admin shows the row with `input_schema` populated; briefing CLI smoke (no key path) still raises `ProviderConfigurationError` cleanly (no service regression).

**Detail worth noting for B2:** the importer's `update_or_create` followed by a field-by-field comparison against the prior snapshot is what lets it distinguish `updated` from `unchanged` — keeps re-imports honest about whether anything actually changed. If B2 starts touching CaseTemplate from the web side, that comparison stays valid because the API and the importer write the same defaults dict.

**B1 hard gate is still open** until Don runs the full flow end-to-end: `import_case_templates` → create his faculty user + Neff `SurgeonPreference` row → ingest a reviewed source PDF → run `generate_briefing --case holep --factors '...' --surgeon ...` and confirm the resident-input dict flows into the briefing prompt with the expected keys. **Do not start B2 until that gate passes.**

## 2026-05-28 — Future: LLM-interviewed SurgeonPreference authoring (parallel track, do not preempt B1–B5)

Surfaced during B1 hard-gate prep when Don pointed out that a published source (AUA guideline, technique paper) only gives the resident the generalizable baseline — it can't tell them anything about his specific case style. That's exactly the content split between `WikiPage` claims (cited published evidence) and `SurgeonPreference` rows (attributable personal preference), and the briefing already renders them as separate sections.

Where it falls apart: the only current path to populate `SurgeonPreference.preferences` is "type structured JSON into the admin form" (`/admin/cases/surgeonpreference/`). That's a usability dead-end. No attending will do it, and the friction blocks (a) onboarding additional faculty, (b) Don himself from authoring preferences across more than one case type.

**Proposal:** a faculty-facing chat surface where a frontier LLM (Opus or Sonnet — interview quality requires it, local models won't do) conducts a structured interview against the case template's `decision_points`, `complication_patterns`, and `attending_question_categories`. For HoLEP that's roughly "For each of these five decision points, what's your default and why?" plus follow-ups. The LLM proposes a structured `preferences` JSON; the surgeon reviews and edits inline; commit writes the row.

**Design constraints to honor when this lands:**
- Frontier model required. Cost is bounded because this is one-time-per-attending-per-case-template.
- Reviewable before commit — surgeon edits the structured output, not auto-save. Editing happens against the structured list, not the chat transcript.
- Faculty-gated (role=faculty). Residents do not author surgeon preferences.
- Case template's `decision_points` are the interview spine, plus a free-form bucket for items that don't map to a decision point (room setup, antibiotic protocol, "what I expect from a resident by case N").
- Audit: `simple-history` already covers the resulting `SurgeonPreference` row. Consider also logging the interview transcript itself in a sibling model (parallel to `IngestRun`) so the structured output can be traced back to the conversation that produced it.

**Sister item (related, also a usability bet):** mirror `import_case_templates` with a `surgeon_preferences.yaml` importer under `modules/cases/<case_type>/surgeon_preferences/<surgeon_email>.yaml`. Same problem (admin tedium), different solution (file-based authoring for users who prefer text editors). Both paths write to the same model; an attending picks whichever ergonomics they prefer.

**Sequencing constraint.** This is Phase C–parallel "authoring polish," not in the resident-experience flow. It comes **after** B1–B5 ship and Don has tested the resident-facing briefing surface end-to-end. The resident experience must work first; then we reduce authoring friction. Do not let this preempt the existing roadmap.
