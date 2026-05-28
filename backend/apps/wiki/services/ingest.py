"""Ingest service: turn a Document into proposed + audited + composed Claims+prose.

Three LLM passes, each through the provider abstraction so any pass can run on
Anthropic, OpenAI, LM Studio, or OpenRouter independently:

  extract_text(doc)             → plain text (PDF via pypdf for now)
  propose_claims(provider, ...) → list of candidate claims with quote + locator
  audit_claims(provider, ...)   → per-claim verdict (ok / weak / unsupported)
  compose_page(provider, ...)   → markdown prose with [[claim_id]] cite markers

The management command `ingest_document` is the only thing that should call
into this; all DB writes happen inside the command's transaction so partial
ingests do not leave half-attributed claims behind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .providers import Message, Provider, get_provider


PROPOSE_SYSTEM_PROMPT = """You extract factual claims from a urology source document for a
procedural case-prep tool. Each claim must be specifically supported by a short
quoted span from the document; you will be asked to cite the quote and its page.

Rules:
- A claim is a single factual statement (one sentence).
- Each claim must be useful for preparing for a urologic procedure: anatomy,
  decision points, complications, perioperative management, technique-specific
  details. Skip background and historical claims.
- The supporting quote must be an exact substring of the document text and
  fully justify the claim. Do not paraphrase the quote.
- Prefer claims grounded in clearly cited evidence (guidelines, RCTs, expert
  consensus). If a claim is opinion or expert-anecdote, set evidence_grade
  accordingly.

Return strict JSON of the form:
  {"claims": [
     {"claim_id": "kebab-case-id",
      "statement": "Single factual sentence.",
      "source_quote": "Exact span from the document.",
      "source_locator": {"page": <int or null>, "section": "..." },
      "evidence_grade": "guideline|rct|cohort|expert|opinion"}
  ]}
No prose outside the JSON.
"""


AUDIT_SYSTEM_PROMPT = """You are an adversarial auditor reviewing claims extracted from a
urology source document. For each (claim, quote) pair you must decide whether
the quote fully and unambiguously supports the claim.

Be strict: residents will use these claims to prepare for live surgery. A claim
that overstates, generalizes, or extrapolates beyond what the quote says is
WEAK. A claim with no plausible support in the document is UNSUPPORTED.

Return strict JSON of the form:
  {"verdicts": [
     {"claim_id": "...",
      "verdict": "ok|weak|unsupported",
      "rationale": "One sentence."}
  ]}
No prose outside the JSON.
"""


COMPOSE_SYSTEM_PROMPT = """You write a single wiki page that summarizes a urology source
document for resident case prep. You will receive: (1) the page's title and
topic anchor, (2) a list of claims that passed the adversarial audit, each
with a claim_id slug and supporting source quote.

Produce markdown for the page body. Hard rules:
- Every factual sentence MUST end with an inline citation in the form
  `[[claim_id]]` matching one of the provided claim_ids. Do NOT cite claim_ids
  you were not given. Do NOT make factual statements without a citation.
- Group claims into short sections with `## Heading` lines. Keep prose tight
  and clinical, not promotional.
- Do not invent statements that go beyond the audited claims.
- Length: short — 200-500 words depending on how many claims you were given.

Return only the markdown body, no surrounding prose, no code fences, no
"Here is the page" preamble.
"""


@dataclass
class ProposedClaim:
    claim_id: str
    statement: str
    source_quote: str
    source_locator: dict
    evidence_grade: str = "opinion"


@dataclass
class ClaimVerdict:
    claim_id: str
    verdict: str
    rationale: str


@dataclass
class IngestResult:
    proposed: list[ProposedClaim] = field(default_factory=list)
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    page_markdown: str = ""

    propose_provider: str = ""
    audit_provider: str = ""
    compose_provider: str = ""
    propose_model: str = ""
    audit_model: str = ""
    compose_model: str = ""

    propose_tokens_in: int = 0
    propose_tokens_out: int = 0
    audit_tokens_in: int = 0
    audit_tokens_out: int = 0
    compose_tokens_in: int = 0
    compose_tokens_out: int = 0
    propose_cost_usd: float = 0.0
    audit_cost_usd: float = 0.0
    compose_cost_usd: float = 0.0

    @property
    def total_cost_usd(self) -> float:
        return self.propose_cost_usd + self.audit_cost_usd + self.compose_cost_usd


def extract_text_from_pdf(path: Path) -> str:
    """Extract plain text from a PDF using pypdf. Layout is not preserved."""

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"[page {i}]\n{text}")
    return "\n\n".join(parts)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported source file type: {suffix}")


def _strict_json_loads(raw: str) -> dict:
    """Parse JSON, tolerating a leading ```json fence if the model added one."""

    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("```", 2)[-1]
        if candidate.endswith("```"):
            candidate = candidate[: -len("```")]
    return json.loads(candidate.strip())


def propose_claims(
    document_text: str,
    *,
    provider: Provider,
    model: str,
) -> tuple[list[ProposedClaim], "ProviderUsageSummary"]:
    # cache=True on the document text + cache_system=True: the audit pass that
    # follows hits the same document_text within Anthropic's 5-minute ephemeral
    # window and reads it from cache, paying ~10% of the input price for the
    # bulk of the prompt.
    response = provider.complete(
        model=model,
        system=PROPOSE_SYSTEM_PROMPT,
        messages=[Message(role="user", text=document_text, cache=True)],
        max_tokens=4096,
        json_mode=True,
        cache_system=True,
    )
    payload = _strict_json_loads(response.text)
    claims = [
        ProposedClaim(
            claim_id=str(c.get("claim_id", "")).strip(),
            statement=str(c.get("statement", "")).strip(),
            source_quote=str(c.get("source_quote", "")).strip(),
            source_locator=dict(c.get("source_locator") or {}),
            evidence_grade=str(c.get("evidence_grade", "opinion")).strip(),
        )
        for c in (payload.get("claims") or [])
        if c.get("claim_id") and c.get("statement")
    ]
    return claims, _summary(provider, model, response)


def audit_claims(
    document_text: str,
    proposed: list[ProposedClaim],
    *,
    provider: Provider,
    model: str,
) -> tuple[list[ClaimVerdict], "ProviderUsageSummary"]:
    # Split into two user messages so the document_text — already cached by the
    # propose pass — gets cache_control on its own block; the variable
    # claims-to-audit list lives in a separate (uncached) block.
    static_payload = json.dumps({"document_text": document_text})
    variable_payload = json.dumps(
        {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "statement": c.statement,
                    "source_quote": c.source_quote,
                    "source_locator": c.source_locator,
                }
                for c in proposed
            ]
        }
    )
    response = provider.complete(
        model=model,
        system=AUDIT_SYSTEM_PROMPT,
        messages=[
            Message(role="user", text=static_payload, cache=True),
            Message(role="user", text=variable_payload),
        ],
        max_tokens=4096,
        json_mode=True,
        cache_system=True,
    )
    parsed = _strict_json_loads(response.text)
    verdicts = [
        ClaimVerdict(
            claim_id=str(v.get("claim_id", "")).strip(),
            verdict=str(v.get("verdict", "weak")).strip().lower(),
            rationale=str(v.get("rationale", "")).strip(),
        )
        for v in (parsed.get("verdicts") or [])
        if v.get("claim_id")
    ]
    return verdicts, _summary(provider, model, response)


def compose_page(
    *,
    page_title: str,
    page_topic: str,
    audited_claims: list[ProposedClaim],
    provider: Provider,
    model: str,
) -> tuple[str, "ProviderUsageSummary"]:
    payload = {
        "page_title": page_title,
        "page_topic": page_topic,
        "audited_claims": [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "source_quote": c.source_quote,
                "evidence_grade": c.evidence_grade,
            }
            for c in audited_claims
        ],
    }
    response = provider.complete(
        model=model,
        system=COMPOSE_SYSTEM_PROMPT,
        messages=[Message(role="user", text=json.dumps(payload))],
        max_tokens=4096,
        cache_system=True,
    )
    return response.text.strip(), _summary(provider, model, response)


@dataclass
class ProviderUsageSummary:
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _summary(provider: Provider, model: str, response) -> ProviderUsageSummary:
    return ProviderUsageSummary(
        provider=provider.name,
        model=model,
        tokens_in=response.usage.input_tokens,
        tokens_out=response.usage.output_tokens,
        cost_usd=provider.estimate_cost_usd(model, response.usage),
    )


def run_ingest(
    document_text: str,
    *,
    page_title: str = "",
    page_topic: str = "",
) -> IngestResult:
    """Three-pass ingest: propose -> adversarial audit -> compose page prose.

    Each pass uses its own provider + model resolved from Django settings, so a
    deployment can mix Anthropic + LM Studio + OpenRouter across stages.
    """

    propose_provider = get_provider(settings.LLM_INGEST_PROPOSE_PROVIDER)
    audit_provider = get_provider(settings.LLM_INGEST_AUDIT_PROVIDER)
    compose_provider = get_provider(settings.LLM_INGEST_COMPOSE_PROVIDER)

    result = IngestResult(
        propose_provider=propose_provider.name,
        audit_provider=audit_provider.name,
        compose_provider=compose_provider.name,
        propose_model=settings.LLM_INGEST_PROPOSE_MODEL,
        audit_model=settings.LLM_INGEST_AUDIT_MODEL,
        compose_model=settings.LLM_INGEST_COMPOSE_MODEL,
    )

    proposed, propose_usage = propose_claims(
        document_text, provider=propose_provider, model=result.propose_model
    )
    result.proposed = proposed
    result.propose_tokens_in = propose_usage.tokens_in
    result.propose_tokens_out = propose_usage.tokens_out
    result.propose_cost_usd = propose_usage.cost_usd

    if not proposed:
        return result

    verdicts, audit_usage = audit_claims(
        document_text, proposed, provider=audit_provider, model=result.audit_model
    )
    result.verdicts = verdicts
    result.audit_tokens_in = audit_usage.tokens_in
    result.audit_tokens_out = audit_usage.tokens_out
    result.audit_cost_usd = audit_usage.cost_usd

    ok_ids = {v.claim_id for v in verdicts if v.verdict == "ok"}
    audited_ok = [c for c in proposed if c.claim_id in ok_ids]
    if audited_ok:
        markdown, compose_usage = compose_page(
            page_title=page_title or "Wiki page",
            page_topic=page_topic or "",
            audited_claims=audited_ok,
            provider=compose_provider,
            model=result.compose_model,
        )
        result.page_markdown = markdown
        result.compose_tokens_in = compose_usage.tokens_in
        result.compose_tokens_out = compose_usage.tokens_out
        result.compose_cost_usd = compose_usage.cost_usd
    return result
