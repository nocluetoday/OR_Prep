# OR Prep — Codex agent guide

This is a proof-of-concept procedural case-prep tool for urology residents. Resident inputs a case → tool emits a structured briefing with cited sources. Not a tutor.

## Read first

[OR Procedural Case Prep.md](OR%20Procedural%20Case%20Prep.md) is the authoritative scope, plan, and non-goals. Everything in this repo is downstream of that doc. If anything below conflicts with it, that doc wins.

## Codex / Claude handoff

`AGENTS.md` is the Codex guide. `CLAUDE.md` is the Claude Code guide. Keep the two top-level files intentionally equivalent so either agent can resume the same plan without reinterpreting scope.

The area-specific guides currently live as `CLAUDE.md` files only: `backend/CLAUDE.md`, `frontend/CLAUDE.md`, and `docker/CLAUDE.md`. Codex should read those same subdir guides unless matching `AGENTS.md` files are added later.

## Non-negotiable constraints

- **Single instance, single specialty, MIT, ~$100/month.** Don't propose multi-tenancy or production hardening beyond a single VPS.
- **No tutor surfaces.** No "ask anything" Q&A, no commit-before-reveal, no calibration tracking, no learn-it / look-it-up framing. Out of scope.
- **Telemetry first-class.** Every briefing request is captured before any beta user touches the system.
- **Correctness over features.** Every factual claim in a briefing must trace to a reviewed source. A confidently-wrong briefing is the worst failure mode.
- **No PHI** in inputs. Resident inputs are case characteristics, not patient identifiers.

## Stack and layout

- Backend (Django + DRF + Postgres) in `backend/`. JWT auth, custom user model, role-based permissions. Case templates + surgeon preferences in `apps.cases`; raw uploads in `apps.documents`; LLM-curated knowledge pages + version-pinned `Claim`s in `apps.wiki`. The legacy curriculum schema in `apps.modules` is retained for compatibility but not used by the briefing path. Every model carries `django-simple-history` for audit.
- Frontend (Vite + React + TS) in `frontend/`. Router + auth context already wired; briefing input form and renderer are Phase B work.
- Compose stack in `docker/`. `../modules:/modules:ro` mounted into backend so the YAML importer reads faculty content without being able to write to git.

See [CODEBASE_MAP.md](CODEBASE_MAP.md) for the directory map and per-subdir CLAUDE.md files (`backend/CLAUDE.md`, `frontend/CLAUDE.md`, `docker/CLAUDE.md`) for area-specific commands and conventions.

## Working notes

- New design discussions go in `docs/journal.md`. Decisions worth surviving sessions go in a top-level doc or the relevant subdir CLAUDE.md.
- `import_modules` still seeds the legacy starter modules; the briefing path does not read them. Authoring case templates and surgeon preferences happens through the Django admin (and, later, a YAML importer mirroring `import_modules`).
- Phase A introduced `apps.cases` (`CaseTemplate`, `SurgeonPreference`) as a new model rather than reshaping `Module`. The two starter modules in `modules/` are kept on disk for now; they aren't a source of truth for briefings.
- **No RAG.** A briefing loads only the relevant case template + surgeon preference data + relevant published claims into context. Topic-scoped, not corpus-scoped. If you find yourself reaching for a vector store, you're off the rails.
- **LLM-wiki content model.** The reference architecture is Karpathy's LLM-wiki gist (`442a6bf555914893e9891c11519de94f`). The LLM writes the wiki page content; humans curate sources and review. Every ingest appends an `IngestRun` log row. Atomic `Claim` rows hang off pages as citation hooks for the briefing's validated `cite(claim_id)` tool call.
- **Anthropic SDK calls are gated on `ANTHROPIC_API_KEY`.** The ingest and briefing commands raise a clear error when the key is missing; they never silently call the network from tests or migrations. Default models: `claude-sonnet-4-6` for briefings, `claude-opus-4-7` reserved for ingest if quality demands. Both env-configurable.

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
