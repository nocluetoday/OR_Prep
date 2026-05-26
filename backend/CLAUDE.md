# backend/

Django 5.2 + DRF. Source of truth for users, modules, progress, uploads.

## Layout

- `config/` — project: `settings/{base,dev,prod}.py`, `urls.py`, `views.py` (health), wsgi/asgi
- `apps/users/` — custom User model (email login, role), auth endpoints, role permission classes
- `apps/modules/` — curriculum schema: Module + LearningObjective + KnowledgeCheck + Reference; YAML importer
- `apps/documents/` — raw uploaded source files (schema inherited; upload flow + extraction land in Phase A/B)
- `apps/wiki/` — LLM-curated knowledge pages with page-level review status (schema inherited; ingest + claim attribution land in Phase A)
- `apps/` — additional apps planned in Phase A: case templates, surgeon preferences, telemetry
- `.venv/` — local virtualenv (gitignored)
- `.env.example` — copy to `.env` to override defaults
- `db.sqlite3` — dev database used only when `DATABASE_URL` is unset (native dev fallback); Postgres ships via docker-compose

## API endpoints (current)

- `GET /api/health/` — public; returns `{status, db, db_vendor, now}`
- `POST /api/auth/register/` — public; resident self-registration; body `{email, password, first_name, last_name}`
- `POST /api/auth/login/` — public; body `{email, password}` → `{access, refresh}`
- `POST /api/auth/refresh/` — body `{refresh}` → new `{access, refresh}` (refresh rotated, old blacklisted)
- `POST /api/auth/logout/` — body `{refresh}` → blacklists the refresh token
- `GET /api/me/` — auth required; returns the current user
- `GET /api/admin/ping/` — auth required + `role == admin`; permission probe (and a useful ops endpoint)

## Commands

Run from `backend/`:

```
.venv/bin/python manage.py runserver 127.0.0.1:8000   # dev server
.venv/bin/python manage.py migrate                    # apply migrations
.venv/bin/python manage.py makemigrations             # generate migrations
.venv/bin/python manage.py createsuperuser            # admin login
.venv/bin/python manage.py import_modules             # seed Module schema from modules/*.yaml
.venv/bin/python manage.py check                      # config validation
.venv/bin/pip install -r requirements-dev.txt         # dev deps
.venv/bin/ruff check .                                # lint
.venv/bin/pytest                                      # tests (none yet)
```

`import_modules` reads `MODULES_DIR` (defaults to `../modules` natively; compose sets it to `/modules`). Skips `_template/`. Idempotent on YAML changes (re-runs detect adds/edits/deletes for objectives, knowledge checks, and references). Pass `--path /custom/path` or `--dry-run` for variants.

## Conventions

- Settings: never edit `base.py` for env-specific values; override in `dev.py`/`prod.py` or read from env via `django-environ`.
- New apps live under `apps/<name>/`. Add them as `apps.<name>` in `INSTALLED_APPS`, and set `label = "<name>"` in the app's `AppConfig` so `AUTH_USER_MODEL = "users.User"` etc. resolve cleanly.
- API URLs are namespaced under `/api/`.
- DRF auth: JWT bearer via simplejwt (`Authorization: Bearer <access>`); default permission is `IsAuthenticated`. Public endpoints opt out with `@permission_classes([AllowAny])` or `permission_classes = [AllowAny]`.
- Role-based authorization: import from `apps.users.permissions` (`IsResident`, `IsFaculty`, `IsAdmin`). Roles are exact-match, not hierarchical.
- Registration creates residents only. Role elevation (to faculty/admin) is an admin action in the Django admin.
- Default settings module: `config.settings.dev` (set in `manage.py`/`wsgi.py`/`asgi.py`).
