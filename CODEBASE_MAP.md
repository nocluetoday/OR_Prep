# Codebase Map

Top-down view of the repo. For per-area conventions see the CLAUDE.md inside each subdirectory.

## Top level

```
OR Procedural Case Prep.md       Authoritative scope and four-phase plan
README.md                Project description, stack, local dev, deploy story
CLAUDE.md                Agent guide (this file's neighbor)
CODEBASE_MAP.md          This file
LICENSE                  MIT
.gitignore               Standard ignores; /uploads/ /media/ /wiki/ anchored at root
.claude/settings.json    Permission deny rules for env / secrets / uploads / wiki
docs/                    Journal and design notes
docker/                  Dev compose stack + Dockerfiles
backend/                 Django project
frontend/                Vite + React app
modules/                 Faculty-authored content (schema layer), seeded into DB
schemas/                 YAML schemas for module + catalog
```

## Backend (Django + DRF)

```
backend/
  manage.py
  requirements.txt           Django, DRF, simplejwt, simple-history, psycopg, PyYAML, ...
  requirements-dev.txt
  pytest.ini
  .env.example
  config/
    settings/
      base.py                AUTH_USER_MODEL, JWT, MODULES_DIR, history middleware
      dev.py                 DEBUG, CORS for :5173, console email backend
      prod.py                Production stub
    urls.py                  /api/health/, includes apps.users.urls
    views.py                 health endpoint (returns db_vendor + now)
    wsgi.py, asgi.py
  apps/
    users/                   custom User (email login, role enum), JWT endpoints,
                             role permission classes, customized Django admin
    cases/                   CaseTemplate (per case type) + SurgeonPreference
                             (per attending, per case type). The briefing
                             surface in management/commands/generate_briefing.py
                             loads exactly one of each into the LLM context.
    wiki/                    WikiPage (now attached to CaseTemplate or legacy Module)
                             + Claim (per factual statement, with FK to Document,
                             source quote/locator, and audit-status lifecycle).
                             services/anthropic_client.py centralizes SDK config;
                             services/ingest.py runs the propose+audit pipeline;
                             management/commands/ingest_document.py is the CLI.
    documents/               Document (raw uploads) extended with source_date,
                             citation, review_status, reviewed_by, last_reviewed_at.
                             Attached to CaseTemplate (Phase A onward) or legacy
                             Module via mutually-exclusive FKs.
    modules/                 Legacy curriculum schema (Module / LearningObjective /
                             KnowledgeCheck / Reference) + import_modules YAML
                             importer. The briefing path does not read these;
                             they are retained for compatibility.
```

Every model carries `HistoricalRecords()` (django-simple-history) for audit. Admin gets a History button per row.

## Frontend (Vite + React + TS)

```
frontend/
  package.json, vite.config.ts, tsconfig*.json
  index.html
  src/
    main.tsx, App.tsx        BrowserRouter + AuthProvider + Header + Routes
    api/client.ts            apiFetch wrapper; bearer attach; refresh-on-401 singleton
    auth/AuthContext.tsx     useAuth hook; login/register/logout; bootstrap from localStorage
    components/              Header (user + role + logout), ProtectedRoute
    pages/                   Login, Register, Home (placeholder)
```

The home page is a placeholder. The briefing input form (Phase B) replaces it.

## Docker (dev stack)

```
docker/
  docker-compose.yml         postgres (internal only) + backend + frontend
  backend.Dockerfile         python:3.13-slim, code mounted from ../backend
  frontend.Dockerfile        node:24-alpine, code mounted from ../frontend
  .env.example               POSTGRES_USER/PASSWORD/DB, DJANGO_SECRET_KEY
  README.md, CLAUDE.md       Compose commands and conventions
```

`../modules:/modules:ro` is bind-mounted so the importer reads faculty content read-only.

## Content (schema layer)

```
modules/
  catalog.yaml               Top-level module catalog
  _template/                 Authoring template for new modules
  urology/
    bph/module.yaml          BPH/LUTS evaluation case (starter)
    ethics-in-consent/       Consent + disclosure case (starter)

schemas/
  module.schema.yaml         YAML schema for module files
  catalog.schema.yaml        YAML schema for catalog
```

The starter modules are placeholder content for the legacy `apps.modules` schema; the briefing path no longer reads them. Phase A authoring happens via the Django admin for `CaseTemplate` and `SurgeonPreference` rows under `apps.cases` (a YAML importer mirroring `import_modules` lands later if author bandwidth justifies it).

## Runtime user data (not committed)

```
uploads/      raw uploaded source files (PDFs, etc.) — bind-mounted, deny-listed
wiki/         LLM-curated markdown — bind-mounted, deny-listed
              (DB row tracks each page with status and version history)
```

Both are gitignored and the path patterns are anchored to repo root so nested app dirs like `backend/apps/wiki/` are not accidentally excluded.
