# OR Prep — agent guide

This is a proof-of-concept procedural case-prep tool for urology residents. Resident inputs a case → tool emits a structured briefing with cited sources. Not a tutor.

## Read first

[OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md) is the authoritative scope, plan, and non-goals. Everything in this repo is downstream of that doc. If anything below conflicts with it, that doc wins.

## Non-negotiable constraints

- **Single instance, single specialty, MIT, ~$1k/month.** Don't propose multi-tenancy or production hardening beyond a single VPS.
- **No tutor surfaces.** No "ask anything" Q&A, no commit-before-reveal, no calibration tracking, no learn-it / look-it-up framing. Out of scope.
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
- `import_modules` seeds two starter urology modules (HoLEP/BPH, ethics-in-consent) as placeholder content. Phase A replaces them with case-template-shaped content (HoLEP, URS for stone, PCNL, etc.) and adds surgeon-preference content.
- The `Module` model currently uses curriculum-flavored field names (`learning_objectives`, `knowledge_checks`). In Phase A it will be either renamed/extended to a `CaseTemplate` model or kept and joined with a new `SurgeonPreference` model. Resolve when the case-template schema is being designed.
- **No RAG.** A briefing loads only the relevant case template + surgeon preference data + relevant wiki claims into context. Topic-scoped, not corpus-scoped. If you find yourself reaching for a vector store, you're off the rails.

## Hard non-goals (do not propose)

- Tutor mode, learn-it mode, look-it-up mode, calibration tracking, commit-before-reveal interactions.
- Adoption mechanics beyond the KU beta cohort.
- Multi-tenancy or multi-program support.
- SSO/SAML, password reset, transactional email.
- Mobile native apps.
- Generalization to non-urology specialties in the PoC.
- Real-time intraoperative anything.
- Production hardening beyond a single VPS.

If the user asks for any of these explicitly, do them. Otherwise the scope doc rules.

## Standing rules

- **README updates after every push.** When a commit lands, the README must reflect what landed. Don't ship a chunk without README being current.
- **All changes get committed via Git.** No long-lived uncommitted state.

<!-- Config review due: 2026-11 -->
