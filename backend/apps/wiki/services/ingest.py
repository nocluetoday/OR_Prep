"""Ingest service: turn a Document into proposed + audited Claims.

The pipeline is three steps, each its own LLM call so the prompts stay focused
and the audit step is genuinely adversarial against the proposal step:

  extract_text(doc)        → plain text (per file type; PDF via pypdf for now)
  propose_claims(...)      → list of candidate claims with quote + locator
  audit_claims(...)        → per-claim verdict (ok / weak / unsupported)

The management command `ingest_document` is the only thing that should call
into this; all DB writes happen inside the command's transaction so partial
ingests do not leave half-attributed claims behind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .anthropic_client import estimate_cost_usd, get_client


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
    verdict: str  # "ok" | "weak" | "unsupported"
    rationale: str


@dataclass
class IngestResult:
    proposed: list[ProposedClaim] = field(default_factory=list)
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    page_markdown: str = ""
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
        # Tag pages so propose_claims can carry a page locator into each claim.
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
        # Strip opening fence (with or without language tag) and trailing fence.
        candidate = candidate.split("```", 2)[-1]
        if candidate.endswith("```"):
            candidate = candidate[: -len("```")]
    return json.loads(candidate.strip())


def propose_claims(document_text: str, model: str | None = None) -> tuple[list[ProposedClaim], dict]:
    client = get_client()
    model = model or settings.ANTHROPIC_INGEST_MODEL
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=PROPOSE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": document_text}],
    )
    raw = "".join(block.text for block in msg.content if block.type == "text")
    payload = _strict_json_loads(raw)
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
    usage = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
    return claims, usage


def audit_claims(
    document_text: str,
    proposed: list[ProposedClaim],
    model: str | None = None,
) -> tuple[list[ClaimVerdict], dict]:
    client = get_client()
    model = model or settings.ANTHROPIC_AUDIT_MODEL
    payload = {
        "document_text": document_text,
        "claims": [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "source_quote": c.source_quote,
                "source_locator": c.source_locator,
            }
            for c in proposed
        ],
    }
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=AUDIT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    raw = "".join(block.text for block in msg.content if block.type == "text")
    parsed = _strict_json_loads(raw)
    verdicts = [
        ClaimVerdict(
            claim_id=str(v.get("claim_id", "")).strip(),
            verdict=str(v.get("verdict", "weak")).strip().lower(),
            rationale=str(v.get("rationale", "")).strip(),
        )
        for v in (parsed.get("verdicts") or [])
        if v.get("claim_id")
    ]
    usage = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
    return verdicts, usage


def compose_page(
    *,
    page_title: str,
    page_topic: str,
    audited_claims: list[ProposedClaim],
    model: str | None = None,
) -> tuple[str, dict]:
    """Third LLM pass: turn audit-OK claims into markdown wiki prose.

    Per the Karpathy LLM-wiki model, the LLM writes the page; the human reviews
    it. Each factual sentence in the output ends with an inline `[[claim_id]]`
    citation marker referencing one of the claims it was given.
    """

    client = get_client()
    model = model or settings.ANTHROPIC_INGEST_MODEL
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
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=COMPOSE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    raw = "".join(block.text for block in msg.content if block.type == "text").strip()
    usage = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
    return raw, usage


def run_ingest(
    document_text: str,
    *,
    page_title: str = "",
    page_topic: str = "",
) -> IngestResult:
    """Three-pass ingest: propose → adversarial audit → compose page prose.

    The compose pass only sees claims that passed audit ("ok"); weak and
    unsupported claims do not appear in the page body but are still persisted
    as Claim rows so faculty can review them.
    """

    result = IngestResult()
    proposed, propose_usage = propose_claims(document_text)
    result.proposed = proposed
    result.propose_tokens_in = propose_usage["input_tokens"]
    result.propose_tokens_out = propose_usage["output_tokens"]
    result.propose_cost_usd = estimate_cost_usd(
        settings.ANTHROPIC_INGEST_MODEL,
        result.propose_tokens_in,
        result.propose_tokens_out,
    )

    if not proposed:
        return result

    verdicts, audit_usage = audit_claims(document_text, proposed)
    result.verdicts = verdicts
    result.audit_tokens_in = audit_usage["input_tokens"]
    result.audit_tokens_out = audit_usage["output_tokens"]
    result.audit_cost_usd = estimate_cost_usd(
        settings.ANTHROPIC_AUDIT_MODEL,
        result.audit_tokens_in,
        result.audit_tokens_out,
    )

    ok_ids = {v.claim_id for v in verdicts if v.verdict == "ok"}
    audited_ok = [c for c in proposed if c.claim_id in ok_ids]
    if audited_ok:
        markdown, compose_usage = compose_page(
            page_title=page_title or "Wiki page",
            page_topic=page_topic or "",
            audited_claims=audited_ok,
        )
        result.page_markdown = markdown
        result.compose_tokens_in = compose_usage["input_tokens"]
        result.compose_tokens_out = compose_usage["output_tokens"]
        result.compose_cost_usd = estimate_cost_usd(
            settings.ANTHROPIC_INGEST_MODEL,
            result.compose_tokens_in,
            result.compose_tokens_out,
        )
    return result
