# OR Prep

> **Scope.** This is a proof-of-concept procedural cognitive prep tool for urology residents, built as a research artifact. A resident inputs a case they are preparing for, and the tool produces a structured 5–20 minute briefing grounded in faculty-reviewed sources, with every claim cited. KU urology residents serve as opt-in beta testers. Deliverables are the system, the design rationale, and beta-use data suitable for publication. This is not a production service and is not clinical decision support.
>
> **Forked from [`resident_learning_wiki`](https://github.com/nocluetoday/resident_learning_wiki)** at commit `725adc1`. The prior project's educational philosophy work remains as an archived research artifact at that repo.

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

Inherited from the fork point:
- Django scaffold with split settings (`config/settings/{base,dev,prod}.py`); compose with Postgres + backend + frontend; `/api/health/` endpoint returning DB-backed status.
- JWT auth: custom `User` model (email login, role enum), register/login/refresh/logout/me endpoints, `IsResident`/`IsFaculty`/`IsAdmin` permission classes.
- Frontend auth flow: login/register pages, protected `/`, `AuthContext` with transparent refresh-on-401.
- Curriculum/knowledge-base data model: `Module`, `LearningObjective`, `KnowledgeCheck`, `Reference` (in `apps.modules`); `Document` (raw upload schema, in `apps.documents`); `WikiPage` with page-level review status (in `apps.wiki`).
- `python manage.py import_modules`: idempotent YAML importer for `modules/**/module.yaml`.
- Two real urology modules (HoLEP/BPH and ethics-in-consent) seed-loaded.

Not yet built (Phase A onward):
- Claim-level source attribution on wiki pages.
- Case template schema (one per case type — HoLEP, URS, PCNL, etc.).
- Surgeon preference schema.
- Ingest pipeline with adversarial audit.
- Citation as a validated tool call in LLM generation.
- Briefing input form, briefing renderer, telemetry tables, debrief form.

The four-phase plan, with definitions of done per phase, is in [OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md).

## Running it locally

You need Docker, or Python 3.13 + Node 20+ for the native path.

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
backend/                Django: apps.users (auth), apps.modules (curriculum schema),
                        apps.documents (raw uploads), apps.wiki (knowledge pages)
frontend/               Vite + React + TS; auth flow + protected routes
docker/                 docker-compose, Dockerfiles, .env.example
modules/                Faculty-authored case content (YAML; imported into DB)
schemas/                YAML schemas for module / catalog
docs/                   Project notes and journal
OR Procedural Case Prep.md      Authoritative scope and four-phase plan; read this first
```

## Deploy

Same as the pivot doc: $20–40/month VPS (Hetzner, DigitalOcean, Linode), Docker Compose with prod settings, Caddy with Let's Encrypt, daily Postgres dump to S3 or Backblaze B2, hostname under a domain Don already owns. No CI/CD beyond a manual deploy script.

## License

MIT. See [LICENSE](LICENSE).

## Research and beta

KU urology residents are the opt-in beta cohort during Phase C. IRB protocol or amendment required before the first briefing is generated for a real case. Authorship plan with the chair and any contributing attending. De-identified data releasable alongside the paper. Target venues: *Journal of Surgical Education* primary; AUA Education and Research subsection abstract; Endourology Society if the talk fits.

## Constraints to honor

- Single instance, single specialty (endourology first, broader urology only if author bandwidth exists).
- ~$1000/month all-in budget.
- Telemetry first-class — captured before the first beta user touches the system.
- Correctness over features — a briefing that confidently asserts something incorrect is the worst possible failure mode, because residents use it to prepare for live surgery.
- No PHI in inputs.
- No tutor surfaces, no calibration tracking, no commit-before-reveal interactions (those belonged to the prior project and are out of scope here).
