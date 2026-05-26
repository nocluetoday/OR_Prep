# OR Prep — agent guide

This is a proof-of-concept procedural case-prep tool for urology residents. Resident inputs a case → tool emits a structured briefing with cited sources. Not a tutor.

## Read first

[PROJECT_PIVOT_2.md](PROJECT_PIVOT_2.md) is the authoritative scope, plan, and non-goals. Everything in this repo is downstream of that doc. If anything below conflicts with the pivot doc, the pivot doc wins.

## Non-negotiable constraints

- **Single instance, single specialty, MIT, ~$1k/month.** Don't propose multi-tenancy or production hardening beyond a single VPS.
- **No tutor surfaces.** No "ask anything" Q&A, no commit-before-reveal, no calibration tracking, no learn-it / look-it-up framing. Those belong to the forked-from project.
- **Telemetry first-class.** Every briefing request is captured before any beta user touches the system.
- **Correctness over features.** Every factual claim in a briefing must trace to a reviewed source. A confidently-wrong briefing is the worst failure mode.
- **No PHI** in inputs. Resident inputs are case characteristics, not patient identifiers.

## Stack and layout

- Backend (Django + DRF + Postgres) in `backend/`. JWT auth, custom user model, role-based permissions. Curriculum schema lives in `apps.modules`; raw uploads in `apps.documents`; LLM-curated knowledge pages in `apps.wiki`. Every model carries `django-simple-history` for audit.
- Frontend (Vite + React + TS) in `frontend/`. Router + auth context already wired; briefing input form and renderer are Phase B work.
- Compose stack in `docker/`. `../modules:/modules:ro` mounted into backend so the YAML importer reads faculty content without being able to write to git.

See [CODEBASE_MAP.md](CODEBASE_MAP.md) for the directory map and per-subdir CLAUDE.md files (`backend/CLAUDE.md`, `frontend/CLAUDE.md`, `docker/CLAUDE.md`) for area-specific commands and conventions.

## Working notes

- New design discussions go in `docs/journal.md`. Decisions worth surviving sessions go in a top-level doc or the relevant subdir CLAUDE.md.
- The `import_modules` command seeds two real urology modules from the fork. They are stand-ins for the case-template content that will replace them in Phase A.
- The `Module` model is repurposed from the prior repo's tutor schema. In Phase A it will be either renamed/extended to a `CaseTemplate` model or kept and joined with a new `SurgeonPreference` model. Don't fight the inherited naming until the case-template schema is being designed.
- The "no RAG" stance carries over. A briefing loads only the relevant module + surgeon preference data + relevant wiki claims into context. Topic-scoped, not corpus-scoped.

## Hard non-goals (do not propose)

- Tutor mode, learn-it mode, look-it-up mode, calibration tracking, commit-before-reveal interactions.
- Adoption mechanics beyond the KU beta cohort.
- Multi-tenancy or multi-program support.
- SSO/SAML, password reset, transactional email.
- Mobile native apps.
- Generalization to non-urology specialties in the PoC.
- Real-time intraoperative anything.
- Production hardening beyond a single VPS.

If the user asks for any of these explicitly, do them. Otherwise the pivot doc rules.

## Standing rules carried over from the prior project

- **README updates after every push.** When a commit lands, the README must reflect what landed. Don't ship a chunk without README being current.
- **All changes get committed via Git.** No long-lived uncommitted state.

<!-- Config review due: 2026-11 -->
