"""Briefing generation service.

Loads the relevant CaseTemplate, SurgeonPreference rows, and published Claims into
context for a single LLM call. The LLM is required to call the `cite(claim_id)`
tool for every factual claim it makes; the server validates each call against
the DB and pins the citation to the WikiPage's current history_id so later
edits do not silently invalidate the prior briefing.

This is the structural heart of Phase A. Telemetry persistence is Phase B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from django.conf import settings

from apps.cases.models import CaseTemplate, SurgeonPreference
from apps.wiki.models import Claim, ClaimAuditStatus, WikiPage
from apps.wiki.services.anthropic_client import estimate_cost_usd, get_client


BRIEFING_SYSTEM_PROMPT = """You produce structured cognitive prep briefings for urology
residents about to do a specific case. The reader will use this in the 5-20
minutes before they walk into the OR.

Output sections (skip a section only if the relevant input is missing):
  1. Case summary — one paragraph.
  2. Anatomy refresher — relevant to this configuration.
  3. Key decision points — 3 to 5, each with the reasoning chain.
  4. Anticipated complications and management.
  5. Surgeon-specific preferences (only if surgeon preferences were provided).
  6. Likely attending questions — 3 to 5.
  7. Sources — populated by the tool, you do not write this section.

Hard rules:
- Every factual claim MUST be supported by a `cite` tool call referencing the
  claim_id of a published Claim. Do NOT make factual statements without citing.
- Briefings tailor to patient_factors and focus_text when present. Do not
  invent factors.
- Length budget: 5-min = ~600 words; 10-min = ~1100 words; 20-min = ~2000 words.
- Educational preparation only. Do not give intraoperative decisions or
  patient-specific clinical recommendations.

You will see the available CaseTemplate, SurgeonPreference data, and the full
list of published Claims (with their claim_ids and statements). Cite by id.
"""


CITE_TOOL_SCHEMA = {
    "name": "cite",
    "description": (
        "Validate and pin a citation to a published Claim. Call this for every "
        "factual statement in the briefing. The server returns either a "
        "validated citation object or an error (claim not found / not published)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "claim_id": {
                "type": "string",
                "description": "The claim_id slug of a published Claim.",
            },
        },
        "required": ["claim_id"],
    },
}


@dataclass
class ValidatedCitation:
    claim_id: str
    statement: str
    source_quote: str
    source_citation: str
    source_date: str
    page_id: int
    page_history_id: int | None
    claim_history_id: int | None
    locator: dict = field(default_factory=dict)


@dataclass
class BriefingResult:
    markdown: str
    citations: list[ValidatedCitation] = field(default_factory=list)
    rejected_cites: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    model: str = ""


def _load_publishable_claims(case_template: CaseTemplate) -> dict[str, Claim]:
    """Return the published claims for this case template, keyed by claim_id."""

    qs = (
        Claim.objects.filter(
            wiki_page__case_template=case_template,
            audit_status__in=(ClaimAuditStatus.AUDITED_OK, ClaimAuditStatus.PUBLISHED),
        )
        .select_related("source_document", "wiki_page")
    )
    return {c.claim_id: c for c in qs}


def _serialize_claims_for_prompt(claims_by_id: dict[str, Claim]) -> list[dict]:
    return [
        {
            "claim_id": c.claim_id,
            "statement": c.statement,
            "wiki_page": c.wiki_page.path,
            "source_date": c.source_document.source_date if c.source_document else "",
            "source_citation": c.source_document.citation if c.source_document else "",
            "evidence_grade": c.source_locator.get("evidence_grade", ""),
        }
        for c in claims_by_id.values()
    ]


def _serialize_case_template(case_template: CaseTemplate) -> dict:
    return {
        "case_type": case_template.case_type,
        "title": case_template.title,
        "summary": case_template.summary,
        "anatomy_focus": case_template.anatomy_focus,
        "decision_points": case_template.decision_points,
        "complication_patterns": case_template.complication_patterns,
        "attending_question_categories": case_template.attending_question_categories,
    }


def _serialize_surgeon_preferences(prefs: list[SurgeonPreference]) -> list[dict]:
    return [
        {
            "surgeon_email": p.surgeon.email,
            "preferences": p.preferences,
        }
        for p in prefs
    ]


def _resolve_cite(claim_id: str, claims_by_id: dict[str, Claim]) -> tuple[ValidatedCitation | None, str | None]:
    claim = claims_by_id.get(claim_id)
    if claim is None:
        return None, "no published claim with that claim_id"
    page = claim.wiki_page
    # Pin to the page's current history version so later edits do not silently
    # invalidate the briefing.
    latest_page_history = page.history.first()
    latest_claim_history = claim.history.first()
    return (
        ValidatedCitation(
            claim_id=claim.claim_id,
            statement=claim.statement,
            source_quote=claim.source_quote,
            source_citation=(claim.source_document.citation if claim.source_document else ""),
            source_date=(claim.source_document.source_date if claim.source_document else ""),
            page_id=page.id,
            page_history_id=getattr(latest_page_history, "history_id", None),
            claim_history_id=getattr(latest_claim_history, "history_id", None),
            locator=claim.source_locator,
        ),
        None,
    )


def generate_briefing(
    *,
    case_template: CaseTemplate,
    surgeon_preferences: list[SurgeonPreference],
    patient_factors: dict,
    surgeon_email: str | None,
    time_minutes: int,
    focus_text: str,
) -> BriefingResult:
    """Run the briefing LLM call with the cite() tool. Returns a BriefingResult.

    No DB writes: the caller decides what to persist (Phase B telemetry).
    """

    claims_by_id = _load_publishable_claims(case_template)

    user_payload = {
        "case_template": _serialize_case_template(case_template),
        "surgeon_preferences": _serialize_surgeon_preferences(surgeon_preferences),
        "patient_factors": patient_factors,
        "surgeon_email": surgeon_email,
        "time_minutes": time_minutes,
        "focus_text": focus_text,
        "available_claims": _serialize_claims_for_prompt(claims_by_id),
    }

    client = get_client()
    model = settings.ANTHROPIC_BRIEFING_MODEL

    messages = [{"role": "user", "content": json.dumps(user_payload)}]
    tokens_in = tokens_out = 0
    validated: list[ValidatedCitation] = []
    rejected: list[dict] = []
    cited_ids: set[str] = set()
    final_text = ""

    # Iterate the tool-use loop; cap at a generous bound so a buggy prompt
    # cannot pin a runaway conversation.
    for _ in range(8):
        msg = client.messages.create(
            model=model,
            max_tokens=8192,
            system=BRIEFING_SYSTEM_PROMPT,
            tools=[CITE_TOOL_SCHEMA],
            messages=messages,
        )
        tokens_in += msg.usage.input_tokens
        tokens_out += msg.usage.output_tokens

        assistant_blocks: list[dict] = []
        tool_results: list[dict] = []

        for block in msg.content:
            if block.type == "text":
                assistant_blocks.append({"type": "text", "text": block.text})
                final_text += block.text
            elif block.type == "tool_use" and block.name == "cite":
                assistant_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
                claim_id = str(block.input.get("claim_id", "")).strip()
                citation, error = _resolve_cite(claim_id, claims_by_id)
                if citation is not None:
                    if claim_id not in cited_ids:
                        validated.append(citation)
                        cited_ids.add(claim_id)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(
                                {
                                    "ok": True,
                                    "claim_id": citation.claim_id,
                                    "statement": citation.statement,
                                    "source_citation": citation.source_citation,
                                    "source_date": citation.source_date,
                                    "page_history_id": citation.page_history_id,
                                }
                            ),
                        }
                    )
                else:
                    rejected.append({"claim_id": claim_id, "reason": error})
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": json.dumps({"ok": False, "reason": error}),
                        }
                    )

        if assistant_blocks:
            messages.append({"role": "assistant", "content": assistant_blocks})
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        if msg.stop_reason != "tool_use":
            break

    markdown = _render_markdown(final_text, validated, rejected)
    return BriefingResult(
        markdown=markdown,
        citations=validated,
        rejected_cites=rejected,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=estimate_cost_usd(model, tokens_in, tokens_out),
        model=model,
    )


def _render_markdown(
    body: str,
    citations: list[ValidatedCitation],
    rejected: list[dict],
) -> str:
    """Append the Sources section to the LLM's body output."""

    parts = [body.rstrip()]
    if citations:
        parts.append("\n\n## Sources\n")
        for i, c in enumerate(citations, start=1):
            page = c.locator.get("page")
            page_str = f", p. {page}" if page else ""
            parts.append(
                f"{i}. **{c.claim_id}** — {c.source_citation or 'Source unspecified'}"
                f"{f' ({c.source_date})' if c.source_date else ''}{page_str}"
                f"\n   > {c.source_quote}"
            )
    if rejected:
        parts.append("\n\n## Citation issues\n")
        parts.append(
            "The following `cite()` calls failed validation and were not "
            "rendered as cited claims. Faculty should review the briefing "
            "transcript for unsupported statements before sharing."
        )
        for r in rejected:
            parts.append(f"- `{r['claim_id']}`: {r['reason']}")
    return "\n".join(parts).strip() + "\n"
