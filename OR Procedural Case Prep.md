# OR Procedural Case-Prep Tool

## What this project is

A tool that takes a resident's input about a case they're about to do and produces a structured 5-minute cognitive briefing, citing reviewed sources. Use moment is the night before or morning of a case. The user is a urology resident at KU. The author of the underlying knowledge base is Don Neff (initially), with the option to add other KU attendings later.

Not a tutor. Not a question bank. Not a study tool. A case-prep tool.

## Posture

- Proof of concept and research artifact. Adoption is not the goal.
- Open source, MIT.
- ~$1000/month all-in budget.
- KU urology residents as opt-in beta testers.
- Outputs: working demo, design rationale, telemetry data, paper, conference abstract.
- Telemetry is first-class. Captured before the first beta user touches the system.

## How this project relates to the prior repo

The prior repo (`resident_learning_wiki`) is forked, not deleted. Treat it as Project 1, archived as a research artifact. The educational philosophy doc remains publishable. The new repo (this one) starts from the prior repo's codebase but discards the tutor surface and learn-it/look-it-up framing.

**Forked from `resident_learning_wiki` at commit `725adc1`.** Archive note added to the prior repo's README pointing here.

## Hard requirements

1. **Open source, MIT.** No proprietary dependencies blocking redistribution. Anthropic API is acceptable.
2. **Telemetry first-class.** Every briefing request is captured: inputs, outputs, citations, validation status, cost, optional post-case debrief.
3. **Correctness over features.** Every claim in a briefing must trace to a reviewed source. A briefing that confidently asserts something incorrect is the worst possible failure mode, because residents are using it to prepare for live surgery.
4. **Cost ceiling: ~$1000/month all-in.** Track spend continuously.
5. **No PHI.** Resident inputs are case characteristics, not patient identifiers. Reinforce in UI on every session.
6. **No clinical decision support.** Persistent disclaimer that this is educational preparation, not intraoperative guidance.
7. **Reproducible.** Clone the repo, follow the README, stack stands up in under an hour with an Anthropic API key.

## Hard non-goals

Do not build, do not plan for:

- Adoption mechanics beyond the KU beta cohort.
- Multi-tenancy or multi-program support.
- SSO/SAML, password reset, transactional email.
- Mobile native apps (mobile web is acceptable if it falls out naturally).
- A tutor surface, learn-it mode, calibration tracking, commit-before-reveal interactions. These belonged to the prior project.
- Generalization to non-urology specialties in the PoC. Endourology first, broader urology only if author bandwidth exists.
- Real-time intraoperative anything. The tool is used before the OR, not in it.
- Production hardening beyond a single VPS.

## What carries over from the prior repo

Keep:

- Django + DRF + React + Vite + Postgres + Docker scaffold.
- JWT auth flow.
- Wiki schema and YAML importer (the wiki is now the knowledge base behind briefings, not a tutor's reference).
- The two existing urology modules' content.
- `django-simple-history` audit logging.
- The "no RAG, no embeddings" position. A single case-prep request loads only the relevant module(s) and surgeon-preference data into context. Topic-scoped, not corpus-scoped.

## What to discard from the prior repo

Delete or strip out:

- The tutor app's commit-before-reveal logic, hint escalation, calibration tracking. These were Phase B of the prior plan and were not yet built; if any scaffolding exists, remove it.
- The educational-philosophy doc as a design constraint. It remains in the prior repo as an archived research artifact and may still be publishable. It does not constrain this project's design.
- Any references to "learn-it mode" or "look-it-up mode" in code, docs, schema, or UI.
- The roadmap doc and PROJECT_PIVOT.md from the prior repo. Replace with this doc.

## Core design

A briefing request takes a small structured input and produces a structured output.

### Input

Resident provides:

- **Case type** (required). HoLEP, URS for stone, PCNL, robotic prostatectomy, etc. Drop-down constrained to cases authored in the knowledge base.
- **Patient factors** (optional, free-form structured fields). Examples for a HoLEP: prostate volume, prior interventions, anticoagulation status, indication (retention vs LUTS), notable comorbidities.
- **Surgeon** (optional). If the surgeon has documented preferences in the knowledge base, those are folded in.
- **Time available** (required). 5, 10, or 20 minutes. Controls briefing depth.
- **Free-text "what I want to focus on"** (optional). One sentence. E.g., "the median lobe is huge, I'm worried about apex dissection."

Input form should be fillable in under 60 seconds. If it isn't, residents won't use it on a busy morning.

### Output

Structured briefing with the following sections (some optional based on time-available and case type):

1. **Case summary in one paragraph.** What this case is, what's notable about this patient's factors, what makes this case routine or non-routine.
2. **Anatomy refresher.** Relevant anatomy for this specific case. For a HoLEP with a large median lobe, this is different from a HoLEP without one.
3. **Key decision points.** The 3-5 intraoperative decisions the resident should anticipate, with the reasoning chain for each. Cited to wiki claims.
4. **Anticipated complications and management.** What can go wrong in this specific case configuration, how to recognize, how to manage.
5. **Surgeon-specific preferences.** If surgeon is provided and has documented preferences, the divergences from the generic approach. Otherwise omitted.
6. **Likely attending questions.** 3-5 questions the resident should be prepared to answer in the OR or pre-op.
7. **Sources cited.** Inline throughout, plus a sources list at the end. Every claim hoverable to its source span.

Output should be readable in the time the resident specified. 5-minute briefing is short and dense; 20-minute briefing has the same structure with more depth.

### Generation

A single LLM call (Claude Sonnet) with:

- System prompt defining the briefing structure and citation rules.
- Module YAML for the case type.
- Surgeon-preference data for the named surgeon, if any.
- Reviewed wiki claims as context, with their source attribution.
- The resident's input.

Output is structured (JSON, then rendered to markdown UI). The model calls a `cite(claim_id)` tool for every factual claim. Claims without valid citations are stripped or flagged before rendering.

### Knowledge base structure

The wiki schema from the prior repo is extended with two new content types:

- **Case templates.** One per case type. Define the briefing skeleton, the decision points typically encountered, the complication patterns. Authored by Don.
- **Surgeon preferences.** Structured per surgeon, per case type. E.g., "Neff's HoLEP preferences: starts with median lobe if present; uses 100W MOSES; specific approach to apex." Each preference is a structured claim with its own source (which may be "Neff personal preference, documented [date]" rather than a literature citation).

Surgeon preferences are opt-in per attending. Ship with Neff's preferences for HoLEP only in v1. Other KU attendings can be added later if they consent and contribute content.

## The four-phase plan (revised)

### Phase A: Correctness layer + knowledge base extension

Carries forward most of the prior Phase A. Extensions:

1. **Claim-level source attribution.** Same as prior plan.
2. **Ingest pipeline with adversarial audit.** Same as prior plan.
3. **Citation as a validated tool call.** Same as prior plan.
4. **Page version pinning in citations.** Same as prior plan.
5. **Source freshness metadata.** Same as prior plan.
6. **Case template schema.** New. One template per case type, defining briefing structure.
7. **Surgeon preference schema.** New. Structured preferences attributable to a named surgeon, with date and review status.

**Demonstrable artifact:** CLI command that produces a briefing for "HoLEP, 80g prostate, on warfarin, attending Neff, 10 minutes available" using validated citations end-to-end.

**Estimated effort:** 3-4 weeks. Slightly longer than the prior Phase A because of the new schemas.

### Phase B: Briefing surface

1. **Input form.** Web UI, fast, defaults sensible, fillable in under 60 seconds.
2. **Briefing renderer.** Markdown output with inline citations, hoverable to source.
3. **Session telemetry.** Every briefing request stored with inputs, outputs, citations, validation results, cost.
4. **Disclaimer modal and footer.** "Educational preparation only. Not intraoperative guidance. Verify clinically relevant details with your attending."

**Demonstrable artifact:** Don logs in, requests a briefing for a HoLEP case with patient factors, reads the briefing, sees all citations resolve to source quotes, telemetry row appears in the database.

**Estimated effort:** 2-3 weeks.

### Phase C: Beta and post-case debrief

1. **Minimal deploy.** Single VPS, Docker Compose, Caddy + Let's Encrypt, daily Postgres dump. Same as prior plan.
2. **Post-case debrief form.** After the resident's case is done, optional follow-up: "Did the briefing match what actually happened? Was anything missing? Was anything wrong?" Three short text fields plus a 1-5 usefulness rating.
3. **Telemetry dashboard.** Read-only admin view showing briefing counts, case type distribution, citation validity rates, debrief feedback.
4. **Recruit 3-5 KU urology residents.** Personal asks. Set expectations: this is research, you may find errors, please report them via debrief, your data will be analyzed and possibly published in de-identified form.

**Demonstrable artifact:** Real briefings generated for real cases, post-case debriefs in the database, no correctness incidents in debrief feedback.

**Estimated effort:** 2 weeks plus calendar time for beta recruitment.

### Phase D: Writeup

1. **Demo for the chair.** 15 minutes. Architecture, live briefing, telemetry, sample debrief data.
2. **Methods section draft.** System architecture, correctness mechanisms, data captured, IRB protocol.
3. **Results section draft.** Whatever the beta data shows. Briefings generated, debrief feedback, citation validity, cost per briefing, time spent per briefing.
4. **Conference abstract.** AUA Education and Research subsection. Possibly the Endourology Society annual meeting given the subspecialty fit.
5. **Paper draft.** Target *Journal of Surgical Education* primarily. *Surgery* or *Academic Medicine* as alternatives.

**Demonstrable artifact:** Slide deck, manuscript draft, submitted abstract.

**Estimated effort:** Ongoing across all phases, concentrated in the final 2-3 weeks.

## Telemetry spec

Captured per briefing request:

**Request-level:**
- `request_id`, `user_id`, `created_at`, `completed_at`.
- Inputs: case type, patient factors (structured), surgeon, time available, focus text.
- Output: full briefing text, structured citations list.
- API metadata: model used, tokens in/out, total cost.
- Generation latency.

**Citation-level (one row per citation in the briefing):**
- `citation_id`, `request_id`, `claim_id`, `page_version`, `validation_status` (valid | invalid | unsupported_dropped), `audit_flag` (null or post-hoc flagged for review).

**Debrief-level (optional, submitted after the case):**
- `debrief_id`, `request_id`, `submitted_at`, `matched_reality_text`, `missing_text`, `wrong_text`, `usefulness_rating` (1-5).

**Cost aggregation (nightly):**
- Daily spend per user, per case type. Surfaced in admin dashboard.

All tables get `exported_at` to track research data exports. A management command produces a de-identified Parquet or CSV export for analysis.

## Cost model

**Assumptions to validate:**

- A briefing request loads ~20-40k input tokens (module YAML + surgeon prefs + relevant wiki claims + system prompt) and produces ~2-5k output tokens.
- At current Claude Sonnet pricing, that's roughly $0.10-0.30 per briefing.
- Use Anthropic prompt caching for the static parts (module YAML, system prompt). Should cut per-briefing cost substantially.
- Ingest cost is the same as the prior plan: $2-5 per document.

**Implication:** with 5 beta testers doing 2 briefings per week, ~$5-15/month on briefings. Comfortably within budget. Bursty ingest weeks (heavy authoring) could be $100-200; still fine.

**Rate limiting and budget guardrails:**

- Per-user daily briefing cap (e.g., 10 briefings per resident per day). Configurable.
- Per-document ingest cap (no document ingested twice without admin override).
- Daily spend alert if yesterday's total exceeded $20.

Model selection: Claude Sonnet (`claude-sonnet-4-5`) for briefings. Opus is overkill. Reserve Opus for ingest if quality demands.

## Deployment for the demo

Same as the prior plan:

- $20-40/month VPS (Hetzner, DigitalOcean, Linode).
- Docker Compose, prod settings.
- Caddy or nginx with Let's Encrypt.
- Daily Postgres dump to S3 or Backblaze B2.
- Hostname under a domain Don already owns.

No CI/CD beyond a manual deploy script. One-paragraph deploy story in the README.

## README content for the new repo

Replace the prior README. Top section:

> **Scope.** This is a proof-of-concept procedural cognitive prep tool for urology residents, built as a research artifact. A resident inputs a case they are preparing for, and the tool produces a structured 5-20 minute briefing grounded in faculty-reviewed sources, with every claim cited. KU urology residents serve as opt-in beta testers. Deliverables are the system, the design rationale, and beta-use data suitable for publication. This is not a production service and is not clinical decision support.
>
> **Forked from `resident_learning_wiki`** at commit `725adc1`. The prior project's educational philosophy work remains as an archived research artifact at that repo.

Architecture section, local dev instructions, deploy story, citation of any preprint, license.

## Research and publication posture

- **Pre-register on OSF.** New registration for this project, separate from the prior project. Describe data captured, analytical plan, success criteria for the PoC.
- **IRB.** New protocol, or an amendment to the prior protocol if one was filed. The data captured here (case characteristics, briefing content, debrief feedback) is different from the prior project. Talk to IRB before the first beta briefing is generated.
- **Authorship plan.** Settle with the chair and any KU attending contributing surgeon-preference content. Residents who substantially contribute to design or data interpretation are coauthors.
- **Data sharing.** De-identified data releasable alongside the paper.
- **Target venues.** *Journal of Surgical Education* primary. *Surgery*, *Academic Medicine*, *JAMA Network Open*, *JMIR Medical Education* as alternatives. AUA Education and Research subsection abstract. Endourology Society if the talk fits.

## Project journal

Carry over the journaling discipline from the prior project. New file `docs/journal.md` in the new repo. First entry should document the fork decision and rationale.

## Definitions of done

**Phase A done:** Ingest a real AUA HoLEP guideline PDF, produce structured claims with source spans, audit pass flags weak attributions, CLI generates a HoLEP briefing with all citations validated and click-throughable.

**Phase B done:** Don logs in, requests a briefing via web UI in under 60 seconds, reads briefing in the time he specified, telemetry row exists with all required fields.

**Phase C done:** At least 3 KU residents have each requested at least 3 briefings before real cases. At least 2 debriefs submitted. No correctness incidents flagged in debriefs.

**Phase D done:** Chair demo delivered. Manuscript draft exists. AUA abstract submitted.

## When to break this plan

Break this plan if:

- Phase A audit pass cannot reliably catch weak attributions (false negative rate too high). The architecture is wrong; rethink before Phase B.
- Beta debriefs in Phase C flag a correctness incident. Stop, diagnose, patch the audit pass, do not move to D until fixed.
- Cost projections at observed Phase C usage exceed $300/month. Redesign before opening to more users.
- After three resident validation conversations, none of them say they'd use the tool. Don't fork. Stay with Project 1.

Do not break this plan for:

- Feature requests outside the four phases.
- Architecture "improvements" without demonstrated need.
- Preparation for scale.
- Pull toward becoming a tutor again. The educational philosophy belongs to Project 1.

## Open questions to resolve before Phase C

- IRB protocol or amendment approval.
- Authorship plan with chair and any contributing attendings.
- Confirmed beta cohort and time commitment.
- Domain name and DNS.
- Anthropic API spend alert mechanism.
- Decision on whether to include any KU attending preferences beyond Don's, and consent process for those attendings.

## What to tell Claude Code at session start

Paste this at the top of any new Claude Code session working on this repo:

> Read `PROJECT_PIVOT_2.md` first. This project is a proof-of-concept procedural cognitive prep tool for urology residents, not a tutor. The user inputs a case, the tool produces a structured briefing with cited sources. Adoption is not a goal. Optimize for correctness, demonstrability, and research output. Telemetry is first-class. Single instance, single specialty, MIT, ~$1000/month all-in budget. Forked from `resident_learning_wiki`. Do not propose tutor surfaces, learn-it modes, calibration tracking, adoption mechanics, multi-tenancy, or production hardening beyond a single VPS unless I explicitly ask.

End of pivot doc.
