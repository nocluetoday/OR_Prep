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
