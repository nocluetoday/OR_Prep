# Project Journal

Carried over from the prior project's discipline. Each entry: date, what changed, why, and what the next decision point is.

## 2026-05-26 — Fork from `resident_learning_wiki` at `725adc1`

The prior project (a learning-mode AI tutor for residents) is archived as Project 1, a research artifact whose educational philosophy doc remains potentially publishable. This project (Project 2) starts from the prior project's codebase at commit `725adc1` and discards the tutor surface in favor of a procedural case-prep briefing tool. Full rationale in [`PROJECT_PIVOT_2.md`](../PROJECT_PIVOT_2.md).

**Fork mechanics.** Manual clone with fresh git history. `git archive` from the prior repo extracted tracked files into a new directory; tutor-specific docs (`docs/architecture.md`, `docs/educational-philosophy.md`, `docs/project-vision.md`, `docs/resident-workflow.md`, `docs/roadmap.md`, `docs/system-architecture.md`, `docs/topic-selection-and-learning-plans.md`, `docs/module-authoring.md`), prompts (`prompts/ai-tutor-system-prompt.md`), governance/safety, faculty workflow, rubrics, examples, and the tutor progress schema (`schemas/progress.schema.yaml`) were dropped. The Django app code, frontend auth flow, Docker stack, wiki/document/module models, and inherited urology module content all carry forward.

**What stayed in Project 1.** Educational philosophy doc, tutor system prompt, governance/safety doc, four-phase pre-pivot roadmap. The prior repo is being marked archived with a link forward to this repo.

**Next decision point.** Phase A: how to model case templates and surgeon preferences against the inherited Module/WikiPage schema. Two reasonable shapes:
1. Extend `Module` with a `case_template` JSONField and add a `SurgeonPreference` model FK'd to Module.
2. Introduce a separate `CaseTemplate` model, leave `Module` as legacy, migrate the two inherited urology modules into the new shape.

Option 2 is cleaner but adds migration work. Decision deferred until the first Phase A claim-attribution piece is being designed, because it constrains how the briefing-generation LLM prompt assembles its context.

**Open questions tracked against PROJECT_PIVOT_2 Phase C blockers.** IRB amendment, authorship plan, beta cohort confirmation, domain name, Anthropic spend-alert mechanism, attending-preferences consent process. None block Phase A start.
