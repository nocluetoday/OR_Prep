"""Briefing generation service.

Loads the relevant CaseTemplate, SurgeonPreference rows, and published Claims
into context for a single tool-use loop. The LLM is required to call the
`cite(claim_id)` tool for every factual claim it makes; the server validates
each call against the DB and pins the citation to the WikiPage's current
history_id so later edits do not silently invalidate the prior briefing.

Provider-agnostic — runs on any backend the registry knows (Anthropic, OpenAI,
LM Studio, OpenRouter). Briefing-time tool-use reliability on local models is
model-dependent; if a loaded LM Studio model doesn't support tools, the loop
will exit immediately with rejected_cites for any inline statements the model
made without going through `cite`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from django.conf import settings

from apps.cases.models import CaseTemplate, SurgeonPreference
from apps.wiki.models import Claim, ClaimAuditStatus
from apps.wiki.services.providers import (
    Message,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
    get_provider,
)


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


CITE_TOOL_SPEC = ToolSpec(
    name="cite",
    description=(
        "Validate and pin a citation to a published Claim. Call this for every "
        "factual statement in the briefing. The server returns either a "
        "validated citation object or an error (claim not found / not published)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "claim_id": {
                "type": "string",
                "description": "The claim_id slug of a published Claim.",
            },
        },
        "required": ["claim_id"],
    },
)


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
    provider: str = ""


def _load_publishable_claims(case_template: CaseTemplate) -> dict[str, Claim]:
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
        {"surgeon_email": p.surgeon.email, "preferences": p.preferences}
        for p in prefs
    ]


def _resolve_cite(
    claim_id: str, claims_by_id: dict[str, Claim]
) -> tuple[ValidatedCitation | None, str | None]:
    claim = claims_by_id.get(claim_id)
    if claim is None:
        return None, "no published claim with that claim_id"
    page = claim.wiki_page
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

    provider = get_provider(settings.LLM_BRIEFING_PROVIDER)
    model = settings.LLM_BRIEFING_MODEL

    messages: list[Message] = [Message(role="user", text=json.dumps(user_payload))]
    cited_ids: set[str] = set()
    validated: list[ValidatedCitation] = []
    rejected: list[dict] = []
    final_text_parts: list[str] = []
    totals = Usage()
    model_reported = model

    for _ in range(8):
        response = provider.complete(
            model=model,
            system=BRIEFING_SYSTEM_PROMPT,
            messages=messages,
            tools=[CITE_TOOL_SPEC],
            max_tokens=8192,
        )
        totals.input_tokens += response.usage.input_tokens
        totals.output_tokens += response.usage.output_tokens
        model_reported = response.model or model

        if response.text:
            final_text_parts.append(response.text)

        if not response.tool_calls:
            break

        # Echo the assistant's turn back into the conversation so the model sees
        # the prior tool_use blocks on the next call (required by both Anthropic
        # and OpenAI-compatible providers).
        messages.append(
            Message(role="assistant", text=response.text, tool_calls=response.tool_calls)
        )

        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            if tc.name != "cite":
                tool_results.append(
                    ToolResult(
                        tool_call_id=tc.id,
                        content=json.dumps({"ok": False, "reason": f"unknown tool: {tc.name}"}),
                        is_error=True,
                    )
                )
                continue
            claim_id = str(tc.input.get("claim_id", "")).strip()
            citation, error = _resolve_cite(claim_id, claims_by_id)
            if citation is not None:
                if claim_id not in cited_ids:
                    validated.append(citation)
                    cited_ids.add(claim_id)
                tool_results.append(
                    ToolResult(
                        tool_call_id=tc.id,
                        content=json.dumps(
                            {
                                "ok": True,
                                "claim_id": citation.claim_id,
                                "statement": citation.statement,
                                "source_citation": citation.source_citation,
                                "source_date": citation.source_date,
                                "page_history_id": citation.page_history_id,
                            }
                        ),
                    )
                )
            else:
                rejected.append({"claim_id": claim_id, "reason": error})
                tool_results.append(
                    ToolResult(
                        tool_call_id=tc.id,
                        content=json.dumps({"ok": False, "reason": error}),
                        is_error=True,
                    )
                )

        messages.append(Message(role="user", tool_results=tool_results))

        if response.stop_reason != "tool_use":
            break

    markdown = _render_markdown("".join(final_text_parts), validated, rejected)
    return BriefingResult(
        markdown=markdown,
        citations=validated,
        rejected_cites=rejected,
        tokens_in=totals.input_tokens,
        tokens_out=totals.output_tokens,
        cost_usd=provider.estimate_cost_usd(model, totals),
        model=model_reported,
        provider=provider.name,
    )


def _render_markdown(
    body: str,
    citations: list[ValidatedCitation],
    rejected: list[dict],
) -> str:
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
