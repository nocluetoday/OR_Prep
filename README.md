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

**Pipelines (CLIs) — done.**
- [x] Ingest CLI (`manage.py ingest_document`): extract → propose claims → adversarial audit → compose markdown prose into `WikiPage.content` → persist draft Claims + IngestRun log row. Three LLM passes. Follows the [Karpathy LLM-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) model: LLM writes the page, human curates.
- [x] Briefing CLI (`manage.py generate_briefing`): tool-use loop with server-validated `cite(claim_id)`; renders markdown with citations + a "Citation issues" footer for unsupported cites; loud warning when the model never called the cite tool.

**Provider abstraction — done (goes beyond original Phase A scope; landed because you asked).**
- [x] Provider ABC (`apps.wiki.services.providers`) supporting `anthropic`, `openai`, `lmstudio`, `openrouter`.
- [x] Per-stage routing (`LLM_BRIEFING_PROVIDER`, `LLM_INGEST_PROPOSE_PROVIDER`, `LLM_INGEST_AUDIT_PROVIDER`, `LLM_INGEST_COMPOSE_PROVIDER`) so different stages can use different backends.
- [x] Per-`CaseTemplate` override for the briefing stage (admin-editable).
- [x] Anthropic prompt caching on system prompt + static-catalog content blocks; cache-hit tokens flow into cost estimate.
- [x] OpenRouter cost-from-response (authoritative `usage.cost` instead of local pricing estimate).

**Phase A close — TODO. Mostly content + config work, not code:**
- [ ] **Drop `ANTHROPIC_API_KEY=…` into `backend/.env`** (or set the `LLM_INGEST_*_PROVIDER`/`LLM_BRIEFING_PROVIDER` env vars to route to LM Studio / OpenAI / OpenRouter, plus the matching key + model).
- [ ] **Author the real HoLEP `CaseTemplate` in Django admin** at `/admin/cases/casetemplate/`: case_type, title, summary, anatomy_focus, decision_points, complication_patterns, attending_question_categories, patient_factor_fields. There's a placeholder smoke-test row at id=1 you can either edit or delete.
- [ ] **Bump your superuser role to `faculty`** at `/admin/users/user/` (created earlier via `createsuperuser`; default role is `resident`). Add a `SurgeonPreference` row attached to the HoLEP CaseTemplate.
- [ ] **Ingest one reviewed source PDF** (AUA HoLEP guideline preferred; any reviewed source works for the first pass). Review the proposed Claims at `/admin/wiki/claim/` and set `audit_status=published` on the ones that pass.
- [ ] **Run `generate_briefing` end-to-end** and confirm citations resolve, audit-flagged claims are excluded, no factual sentence is uncited.

### Phase B — Briefing surface (not started)

Phase B is what turns the auth shell into a real briefing tool. Right now there's nothing for a logged-in user to do.

- [ ] **DRF briefing endpoint.** New `POST /api/briefings/` that wraps the existing `generate_briefing` service; auth required; returns the rendered markdown + structured citation payload. Plus `GET /api/case-templates/` to drive the case-type dropdown.
- [ ] **Briefing input form.** Replace the placeholder `Home` page with the input form: case-type dropdown (from published `CaseTemplate` rows), patient-factor structured fields (driven by `CaseTemplate.patient_factor_fields`), optional surgeon dropdown, time budget (5 / 10 / 20), focus free-text. Fillable in under 60 seconds.
- [ ] **Briefing renderer.** Markdown render of the response; inline `[[claim_id]]` markers turned into hoverable footnote refs that pop the source quote + citation. No-tool-calls warning rendered as a banner.
- [ ] **Session telemetry tables.** New `apps.telemetry` app with `BriefingRequest` + `Citation` rows: every submission stored with full inputs, output markdown, validated citations (with `page_history_id` pins), token + cost, latency. **Must land before any beta user touches the system.**
- [ ] **Disclaimer modal + footer.** First-visit modal: *"Educational preparation only. Not intraoperative guidance. Verify clinically relevant details with your attending."* Persistent short footer.

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

1. **Close Phase A** (your work, mostly): drop an API key in `backend/.env`, author the HoLEP `CaseTemplate` in admin, bump your role to `faculty`, ingest a reviewed source PDF, review the audit verdicts, run `generate_briefing`. No further code changes needed for Phase A unless something breaks in real use.
2. **Start Phase B** (code work): wire the DRF endpoint that wraps `generate_briefing`, build the React input form + renderer to replace the placeholder home page, stand up the telemetry tables, add the disclaimer. The input form and renderer can be scaffolded with placeholder data before your `CaseTemplate` content is real, then validated against it.

Phase B is the next major code track. Phase A's remaining work is content and config — it can run in the background while Phase B is being built.

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
