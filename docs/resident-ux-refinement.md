# Resident UX refinement — Phase B roadmap

This document captures the refined Phase B spec for the OR Prep resident interaction layer and the approved implementation plan for the first step.

It supersedes the bullet list of Phase B items in the [README's Roadmap](../README.md#phase-b--briefing-surface) with explicit ordering, hard gates between steps, performance targets, and explicit non-goals.

**The five steps are ordered.** Do not start step N+1 until step N is working end-to-end and Don has tested it.

---

## Source spec

Refinement spec recorded 2026-05-27. The sketch (greeting → attending → case → case details → briefing) is directionally right; the changes below tighten it.

### 1. Per-case input schema mechanism (architectural foundation)

Each case template owns its own input schema declared in YAML/JSON alongside the template content. The schema declares: field name, label, type (select, text, number, boolean, multi-select), required vs optional, options if applicable, help text. Adding a new case type means authoring a new template with its own schema, not editing form code.

Examples of case-specific schemas:

- **HoLEP**: prostate volume (number, required), prior interventions (multi-select, optional), anticoagulation (select, required), indication (select: retention vs LUTS vs other, required), Qmax (number, optional), PVR (number, optional)
- **Robotic prostatectomy**: PSA (number, required), Gleason (text, required), MRI findings (text, optional), prior pelvic surgery (boolean, required), nerve-sparing intent (select, required)
- **IPP**: prior implants (boolean, required), erectile function workup summary (text, optional), hand function (select, required), partner factors (text, optional)

Each schema declares a "quick set" (4-6 required fields rendered by default) and "expanded" fields (optional, surfaced behind a "More detail" expander).

The backend stores submitted inputs as JSON keyed to the case template version so analysis later can group by case type.

### 2. Single-screen input form

Replace the multi-step modal flow with one screen, all fields visible:

- Greeting line: *"Good morning, Dr. [name]. Quick prep for tomorrow's case?"*
- **Attending**: dropdown, defaults to last used by this resident. Mark attendings with documented preferences with an indicator (e.g. asterisk + tooltip *"Preferences documented"*). Attendings without preferences are still selectable; the briefing will note *"generic approach, confirm with attending."*
- **Case**: searchable dropdown populated from authored case templates. "Other" fallback opens free text and logs the entry so Don can see what's missing from the template library.
- **Case date**: defaults to tomorrow.
- **Time available**: 5 / 10 / 20 min, radio buttons.
- **Case-specific quick fields**: render the selected case template's quick-set schema. Optional "More detail" link expands the optional fields.
- **Focus text**: optional single-line *"Anything specific you want to focus on?"*
- **Generate Briefing** button.

**Performance targets:**

- Form is visible and interactive in under **5 seconds** from app open.
- Resident can complete the quick set in **30-60 seconds**.
- Briefing renders in under **15 seconds**.

Add a one-line value statement above the form for users with fewer than 5 prior briefings: *"Five minutes of prep, grounded in [attending]'s preferences and reviewed literature. Citations on every claim."* Hide it after 5 briefings.

### 3. Output structure: decision-led, not step-led

Restructure the briefing output. The current concept (instruments → equipment → steps → suture) reads like a Surgical Atlas chapter. Replace with this order:

1. **Setup and positioning**, with case-specific variations folded in (e.g. *"For an 80g gland on warfarin, irrigation flow higher than default; have extra Foleys in the room"*).
2. **Decision points (3-5).** Each decision point names the moment, the consideration, the attending's preferred approach (if documented) with citation, and the alternative. **This is the centerpiece.**
3. **Actual steps**, folded into the decision points where relevant. Not a separate flat list.
4. **Equipment and consumables checklist** at the end, screenshot-friendly.
5. **Anticipated complications and management**, specific to this case configuration.
6. **Post-op care to discharge**, brief, only if a pathway exists for this case type.
7. **Likely attending questions (3-5).** The questions a resident should be prepared to answer in pre-op or in the OR.

Every factual claim in the briefing carries a citation tool call to a validated `claim_id` (already implemented in the correctness layer). Citations are hoverable in the UI to reveal source quote.

### 4. Follow-up turn capability

After the briefing renders, allow the resident to ask **2-3 follow-up questions scoped to this case**. Show a single input below the briefing labeled *"Ask a follow-up question about this case."*

System prompt for follow-up turns enforces: stay within the loaded case context and knowledge base. Do not generalize to other urology topics. If the question is out of scope, say so plainly and suggest the resident reference the wiki or attending directly.

After 3 follow-up turns, the input changes to *"Done with this case — I'll ask how it went later"* with a **Close session** button.

Telemetry captures each follow-up turn separately: `turn_id`, `request_id`, `content`, `cost`, `citations called`.

### 5. Post-case debrief

Add a debrief prompt that fires either at end-of-day (if the resident's case was today) or on next app open after the case date passes. **Do not prompt immediately after the case.**

Form:

- *"How did the [case type] go with [attending]?"*
- *"Did the briefing match what actually happened?"* (text)
- *"Anything missing?"* (text)
- *"Anything wrong?"* (text)
- *"Usefulness 1-5"* (radio)
- **Skip** button always available.

Stores to debrief table tied to the original `request_id`. Optional fields. Skipping is logged as a separate event.

### Attending preference indicator (cross-cutting)

When the resident selects an attending without documented preferences, the briefing **must** include a visible note at the top:

> *"No documented preferences for [attending]. This briefing reflects a standard approach. Confirm specifics with your attending pre-op."*

**Non-negotiable for correctness reasons.**

### What not to build

- Attending typeahead UI polish, animations, transitions.
- Multi-step wizard. **One screen.**
- Notification systems beyond the in-app debrief prompt. **No email, no push.**
- Calendar integration. Maybe later, not now.
- Sharing or export beyond the equipment checklist screenshot.
- Anything that turns this into a general tutor in the follow-up turns.

### Order of work

1. Case template schema mechanism. Migration, model changes, YAML schema spec, one example case template (HoLEP) fully authored with its quick-set and expanded schemas.
2. Single-screen input form rendering against the schema.
3. Output structure refactor in the briefing generation prompt and renderer.
4. Follow-up turn capability with scoped system prompt.
5. Post-case debrief prompt, form, storage.

**Do not move to step N+1 until step N is working end-to-end and Don has tested it.**

This refinement does not change any constraints from [OR Procedural Case Prep.md](../OR%20Procedural%20Case%20Prep.md) (overall scope, telemetry spec, correctness layer requirements, non-goals).

---

## Step B1 — Approved implementation plan

**Status: planned, not started. Plan approved 2026-05-27. Execution deferred to a future session.**

### What lands in step B1

1. **Rename `CaseTemplate.patient_factor_fields` → `input_schema`.** Change default from `list` to a module-level callable `_default_input_schema()` returning `{"quick": [], "expanded": []}` (not a lambda — Django migrations cannot serialize lambdas). Single migration: `RemoveField` + `AddField` (no rename — shapes are incompatible). The placeholder smoke-test row at pk=1 is the only existing data; verify with `CaseTemplate.objects.exclude(patient_factor_fields=[]).count() == 0` before generating the migration.

2. **YAML schema spec at `schemas/case_template.schema.yaml`** (new file, mirrors `schemas/module.schema.yaml`). Documents top-level fields (`case_type`, `title`, `specialty`, `summary`, `version`, `review_status`, `anatomy_focus[]`, `decision_points[]`, `complication_patterns[]`, `attending_question_categories[]`, `input_schema`) and the `input_schema` block shape. Each schema field declares: `name` (snake_case slug — becomes the dict key in `patient_factors` passed to the briefing service; must be unique across `quick + expanded`), `label`, `type` (one of `select`, `text`, `number`, `boolean`, `multi_select`), `required` (defaults False), `help_text` (optional), `options[]: [{value, label}]` (required for `select` / `multi_select`, must be non-empty).

3. **Importer: `manage.py import_case_templates`** at `backend/apps/cases/management/commands/import_case_templates.py`. Mirrors `apps/modules/management/commands/import_modules.py`:
   - `rglob("case_template.yaml")` under `MODULES_DIR`, skip any path containing `_template`.
   - `yaml.safe_load`, `update_or_create` on `case_type` slug, atomic per file.
   - Validates: `case_type` slug required; `input_schema` is a dict with both `quick` and `expanded` lists; each field has `name` / `label` / `type` in the allowed five; `select` / `multi_select` carry a non-empty `options` list of `{value, label}`; field `name`s are unique across `quick + expanded` in the same file.
   - Non-zero exit + clear stderr on validation failure.
   - Reports `created` / `updated` / `unchanged` counters.
   - `--dry-run` and `--path` flags for parity with `import_modules`.

4. **Sample HoLEP at `modules/cases/holep/case_template.yaml`** (new file, flat layout — single-specialty PoC). All structured fields populated with realistic content. `input_schema`:
   - `quick`: `prostate_volume_g` (number, required), `indication` (select retention | luts | hematuria | other, required), `anticoagulation` (select none | aspirin | warfarin | doac | dual_antiplatelet, required), `prior_interventions` (multi_select none | turp | greenlight | rezum | uplift | simple_prostatectomy, optional).
   - `expanded`: `qmax_ml_per_s` (number, optional), `pvr_ml` (number, optional), `notable_comorbidities` (text, optional).
   - Field names carry units (`_g`, `_ml`, `_ml_per_s`) so the briefing prompt sees self-documenting keys.
   - Also populate realistic `anatomy_focus`, `decision_points`, `complication_patterns`, `attending_question_categories` so the briefing has actual material to work with when Don tests end-to-end.

5. **Admin: rename in `backend/apps/cases/admin.py` fieldsets.** Swap `"patient_factor_fields"` for `"input_schema"` in the `CaseTemplateAdmin` "Briefing shape (LLM context)" fieldset. No other admin changes.

6. **Docs**:
   - `backend/CLAUDE.md` — add `import_case_templates` under the existing `import_modules` line; note the new YAML location at `modules/cases/`.
   - `README.md` — check off the step-B1 sub-bullets as each lands.
   - `docs/journal.md` — entry documenting the rename, layout decision, field-name-as-contract invariant, and "stop here, wait for Don to test" gate.

### Out of scope for step B1 (do not touch)

- `apps/cases/services/briefing.py`, `generate_briefing.py`, prompts, providers — no service or prompt changes (those are step B3).
- Telemetry / debrief / followup apps and tables — steps B4-B5.
- Briefing output section reorder — step B3.
- Frontend code — step B2.
- Second case template (e.g. robotic prostatectomy, IPP) — the pattern proves with one example.
- `modules/cases/_template/case_template-template.yaml` — extract scaffolding once a second case exists.

### Critical files

- `backend/apps/cases/models.py` (rename field, add `_default_input_schema()` callable)
- `backend/apps/cases/migrations/0003_*.py` (auto-generated; `RemoveField` + `AddField`)
- `backend/apps/cases/admin.py` (rename in fieldsets)
- `backend/apps/cases/management/commands/import_case_templates.py` (new — mirrors `apps/modules/management/commands/import_modules.py`)
- `schemas/case_template.schema.yaml` (new — mirrors `schemas/module.schema.yaml` style)
- `modules/cases/holep/case_template.yaml` (new)
- `README.md`, `backend/CLAUDE.md`, `docs/journal.md` (doc updates)

### Invariants worth capturing in the journal when step B1 ships

- **Field `name` is a contract.** Once a YAML field's `name` is published, changing it silently invalidates any future briefings whose persisted resident input was keyed to the old name. Migration story for renames belongs to step B5 (telemetry / debrief) when submitted inputs start being persisted; flag in the journal so step B5 doesn't get caught unawares.
- **Schema versioning is per-template, not per-schema.** `version` is a manually-managed CharField on `CaseTemplate`. If `input_schema`'s allowed types ever extend (e.g. adding `date`), there's no machine-readable signal that prior submissions used the old shape. Document the caveat inside `schemas/case_template.schema.yaml`.
- **No template scaffolding yet.** Skip `modules/cases/_template/case_template-template.yaml` until a second case is authored; shape is easier to extract from two real examples than one.

### Verification (run from `backend/` when step B1 is executed)

1. `.venv/bin/python manage.py check` — config validation passes.
2. `.venv/bin/python manage.py makemigrations cases` — produces one migration; spot-check the diff is `RemoveField('patient_factor_fields')` + `AddField('input_schema', ...)`.
3. `.venv/bin/python manage.py migrate` — applies cleanly.
4. `.venv/bin/python manage.py import_case_templates --dry-run` — parses HoLEP YAML, no writes.
5. `.venv/bin/python manage.py import_case_templates` — reports `created: 1` (or `updated: 1` if the placeholder smoke-test row at pk=1 already exists with `case_type='holep'`).
6. Re-run with no edits — reports `unchanged: 1`.
7. Edit `summary` in YAML, re-run — reports `updated: 1`.
8. Negative test: temporarily duplicate a field `name` across `quick` and `expanded` — importer exits non-zero with clear stderr. Revert.
9. Negative test: change a `select` field's `options` to `[]` — importer exits non-zero with clear stderr. Revert.
10. `/admin/cases/casetemplate/<id>/change/` — HoLEP row shows `input_schema` populated as JSON.
11. Existing briefing CLI smoke (`manage.py generate_briefing --case holep --time 10` with no API key) still raises `ProviderConfigurationError` — confirms no service regression.

### Hard gate

Stop after step B1 lands and the verification list passes. **Do not** begin step B2 (single-screen input form), step B3 (briefing output reorder), step B4 (follow-up turns), or step B5 (debrief) until Don has tested step B1 against a real ingest + briefing end-to-end and approved.

---

## Steps B2-B5

Detailed implementation plans are written when each step begins — not now, to avoid drift between spec and plan. The source spec above is authoritative for what each step must deliver. The step-B1 plan above is the template for what each step's plan should look like (context, scope, critical files, verification, hard gate).
