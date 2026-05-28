# backend/

Django 5.2 + DRF. Source of truth for users, modules, progress, uploads.

## Layout

- `config/` — project: `settings/{base,dev,prod}.py`, `urls.py`, `views.py` (health), wsgi/asgi
- `apps/users/` — custom User model (email login, role), auth endpoints, role permission classes
- `apps/cases/` — CaseTemplate + SurgeonPreference. `services/briefing.py` owns the briefing tool-use loop with `cite(claim_id)`; `management/commands/generate_briefing.py` is the CLI.
- `apps/wiki/` — WikiPage + Claim + IngestRun (append-only ingest log). `services/providers/` holds the provider abstraction (`base.py` ABC + `anthropic.py` + `openai_compat.py` + `registry.py`); ingest and briefing services never import an SDK directly. `services/ingest.py` runs propose → adversarial-audit → compose-markdown-prose through the provider abstraction; `management/commands/ingest_document.py` is the CLI and writes both the prose into `WikiPage.content` and the audit-flagged Claims off the page.
- `apps/documents/` — Document with source freshness fields (`source_date`, `citation`, `review_status`, `reviewed_by`, `last_reviewed_at`). FK is mutually exclusive between `case_template` and `module`.
- `apps/modules/` — legacy curriculum schema (Module + LearningObjective + KnowledgeCheck + Reference) + `import_modules` YAML importer. Retained for compatibility; not read by the briefing path.
- `apps/` — telemetry app planned in Phase B (per-request rows for inputs, outputs, validation results, cost).
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
.venv/bin/python manage.py import_modules             # seed legacy Module schema from modules/*.yaml
.venv/bin/python manage.py ingest_document <path> \
    --case-type holep --wiki-page-path operative-technique \
    --citation "AUA HoLEP Guideline (2024)" --source-date 2024-08 \
    --uploaded-by faculty@example.com                 # extract+propose+audit Claims from a source
.venv/bin/python manage.py generate_briefing \
    --case holep --time 10 --surgeon neff@example.com \
    --factors 'prostate_volume_g=80,anticoagulation=warfarin' \
    --focus 'large median lobe, worried about apex'   # produce a structured cited briefing
.venv/bin/python manage.py check                      # config validation
.venv/bin/pip install -r requirements-dev.txt         # dev deps
.venv/bin/ruff check .                                # lint
.venv/bin/pytest                                      # tests (none yet)
```

`import_modules` reads `MODULES_DIR` (defaults to `../modules` natively; compose sets it to `/modules`). Skips `_template/`. Idempotent on YAML changes (re-runs detect adds/edits/deletes for objectives, knowledge checks, and references). Pass `--path /custom/path` or `--dry-run` for variants.

`ingest_document` and `generate_briefing` route through `apps.wiki.services.providers`. Four provider kinds are supported: `anthropic`, `openai`, `lmstudio`, `openrouter`. Each pipeline stage (briefing, ingest propose, ingest audit, ingest compose) has its own `LLM_*_PROVIDER` + `LLM_*_MODEL` env vars; defaults are `anthropic` + Sonnet 4.6 across the board (Opus 4.7 for audit). OpenAI, LM Studio, and OpenRouter share one implementation that overrides `base_url` on the openai SDK; LM Studio is treated as free, OpenAI uses a local pricing table, OpenRouter returns authoritative spend in `usage.cost` (we request it via `extra_body={"usage":{"include":True}}` and surface it as `Usage.actual_cost_usd`).

Per-CaseTemplate override: `CaseTemplate.briefing_provider_override` and `briefing_model_override` (settable in admin) take precedence over the global `LLM_BRIEFING_*` settings, so high-stakes cases can pin Anthropic while exploratory cases route to cheap local providers.

Prompt caching: `Message(cache=True)` and `cache_system=True` are honored by the AnthropicProvider (applies `cache_control: ephemeral`). Ingest caches document text across propose+audit (within Anthropic's 5-minute ephemeral window) and caches all three system prompts. Briefing caches the static catalog (case template + surgeon prefs + claim list) + system prompt; the variable per-request inputs live in a separate uncached block. OpenAI-compat providers ignore the flags (OpenAI does automatic server-side caching on long prompts).

Briefing tool-use loops require providers that support function calling; many local LM Studio models do not. When the loop exits with zero tool calls AND the case has publishable claims, the briefing output leads with a prominent warning and the CLI prints a stderr warning — the briefing is unsupported and should not be used as a citable artifact. The relevant API key for whichever provider a stage uses must be set; commands raise `ProviderConfigurationError` if not. LM Studio's "key" is a sentinel — any non-empty string works — and the default is "lm-studio".

## Conventions

- Settings: never edit `base.py` for env-specific values; override in `dev.py`/`prod.py` or read from env via `django-environ`.
- New apps live under `apps/<name>/`. Add them as `apps.<name>` in `INSTALLED_APPS`, and set `label = "<name>"` in the app's `AppConfig` so `AUTH_USER_MODEL = "users.User"` etc. resolve cleanly.
- API URLs are namespaced under `/api/`.
- DRF auth: JWT bearer via simplejwt (`Authorization: Bearer <access>`); default permission is `IsAuthenticated`. Public endpoints opt out with `@permission_classes([AllowAny])` or `permission_classes = [AllowAny]`.
- Role-based authorization: import from `apps.users.permissions` (`IsResident`, `IsFaculty`, `IsAdmin`). Roles are exact-match, not hierarchical.
- Registration creates residents only. Role elevation (to faculty/admin) is an admin action in the Django admin.
- Default settings module: `config.settings.dev` (set in `manage.py`/`wsgi.py`/`asgi.py`).
