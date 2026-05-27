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

Four phases. Each item is checked off only when it actually lands; phases are marked complete only when their definition of done in [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md) is met (which for Phase A requires ingesting a real AUA HoLEP guideline PDF end-to-end).

### Phase A — Correctness layer + knowledge base extension (in progress)

- [x] `apps.cases` with `CaseTemplate` schema (one per case type) and `SurgeonPreference` schema (per attending, per case type), both with `HistoricalRecords`.
- [x] Claim-level source attribution on wiki pages (`apps.wiki.Claim` with FK to `Document` + source-span quote/page).
- [x] Page version pinning in citations — every claim resolved to a specific `WikiPage` history id so later edits don't silently invalidate prior briefings.
- [x] Source freshness metadata on `Document` (`source_date`, `last_reviewed_at`, `review_status`, reviewer).
- [x] Django admin registrations for `CaseTemplate`, `SurgeonPreference`, `Claim`, and `Document` review fields.
- [x] Ingest pipeline stub (`manage.py ingest_document <path>`): extract → propose claims → adversarial audit → write as draft `Claim`s. Gated on `ANTHROPIC_API_KEY`.
- [x] Briefing CLI stub (`manage.py generate_briefing --case ... --surgeon ... --time ...`) with the `cite(claim_id)` tool. Gated on `ANTHROPIC_API_KEY`; the server validates every `cite` against the DB and drops/flags unsupported claims before rendering.
- [ ] HoLEP case template, Neff HoLEP surgeon preferences, and a real reviewed source ingested end-to-end (closes Phase A).

### Phase B — Briefing surface (not started)

- [ ] Input form (web UI, fillable in under 60 seconds).
- [ ] Briefing renderer with inline citations hoverable to source quote.
- [ ] Session telemetry: every briefing request stored with inputs, outputs, citations, validation results, and cost.
- [ ] Disclaimer modal and footer ("Educational preparation only. Not intraoperative guidance.").

### Phase C — Beta and post-case debrief (not started)

- [ ] Minimal VPS deploy: Docker Compose + Caddy + Let's Encrypt + daily Postgres dump.
- [ ] Post-case debrief form (matched-reality / missing / wrong / 1–5 usefulness rating).
- [ ] Admin telemetry dashboard.
- [ ] Recruit 3–5 KU urology residents; first real briefings generated.

### Phase D — Writeup (not started)

- [ ] Chair demo.
- [ ] Methods + results draft.
- [ ] AUA Education and Research subsection abstract submitted.
- [ ] Paper draft (target: *Journal of Surgical Education*).

Definitions of done and the "when to break the plan" criteria live in [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md).

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
