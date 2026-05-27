"""Ingest a source document and create proposed + audited Claims.

Usage:
  python manage.py ingest_document /path/to/source.pdf \\
      --case-type holep \\
      --wiki-page-path operative-technique \\
      --citation "AUA HoLEP Guideline (2024)" \\
      --source-date 2024-08 \\
      --uploaded-by don@example.com

The command:
  1. Hashes the file, copies it under uploads/ (gitignored), and creates a
     `Document` row attached to the named CaseTemplate.
  2. Extracts text and runs the two-pass ingest service (propose, then audit).
  3. Creates a WikiPage (if not already present) under the CaseTemplate, then
     persists each proposed Claim with its audit verdict applied to
     `audit_status`.
  4. Refuses to run when month-to-date ingest cost would blow the configured
     budget envelope unless --force is set.

No Claims are auto-published. Faculty reviews and publishes via the admin.
"""

from __future__ import annotations

import hashlib
import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.cases.models import CaseTemplate
from apps.documents.models import Document, DocumentStatus, ReviewStatus as DocReviewStatus
from apps.wiki.models import (
    Claim,
    ClaimAuditStatus,
    IngestRun,
    IngestRunStatus,
    WikiPage,
    WikiPageStatus,
)
from apps.wiki.services.ingest import extract_text, run_ingest
from apps.wiki.services.providers import ProviderConfigurationError


VERDICT_TO_STATUS = {
    "ok": ClaimAuditStatus.AUDITED_OK,
    "weak": ClaimAuditStatus.AUDITED_WEAK,
    "unsupported": ClaimAuditStatus.AUDITED_WEAK,
}


class Command(BaseCommand):
    help = "Ingest a source document into proposed + audited Claims for a case template."

    def add_arguments(self, parser):
        parser.add_argument("source_path", help="Path to the source file (PDF / TXT / MD).")
        parser.add_argument("--case-type", required=True, help="CaseTemplate.case_type slug.")
        parser.add_argument(
            "--wiki-page-path",
            required=True,
            help="Wiki page path under the case (e.g. 'operative-technique').",
        )
        parser.add_argument("--citation", required=True, help="Human-readable citation string.")
        parser.add_argument(
            "--source-date",
            default="",
            help="Publication / version date of the source (YYYY, YYYY-MM, or YYYY-MM-DD).",
        )
        parser.add_argument(
            "--uploaded-by",
            required=True,
            help="Email of the faculty user uploading the source.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even if month-to-date ingest cost would exceed INGEST_MONTHLY_BUDGET_USD.",
        )

    def handle(self, *args, **opts):
        source_path = Path(opts["source_path"]).resolve()
        if not source_path.is_file():
            raise CommandError(f"source file not found: {source_path}")

        try:
            case_template = CaseTemplate.objects.get(case_type=opts["case_type"])
        except CaseTemplate.DoesNotExist as e:
            raise CommandError(f"no CaseTemplate with case_type={opts['case_type']!r}") from e

        User = get_user_model()
        try:
            uploader = User.objects.get(email=opts["uploaded_by"])
        except User.DoesNotExist as e:
            raise CommandError(f"no user with email={opts['uploaded_by']!r}") from e

        self._check_monthly_budget(force=opts["force"])

        sha = self._sha256(source_path)
        uploads_root = Path(settings.BASE_DIR).parent / "uploads"
        uploads_root.mkdir(exist_ok=True)
        stored_path = uploads_root / f"{sha}{source_path.suffix.lower()}"
        if not stored_path.exists():
            shutil.copy2(source_path, stored_path)

        with transaction.atomic():
            doc, doc_created = Document.objects.get_or_create(
                case_template=case_template,
                sha256=sha,
                defaults={
                    "filename": source_path.name,
                    "mime_type": self._mime(source_path),
                    "size_bytes": source_path.stat().st_size,
                    "raw_path": str(stored_path),
                    "uploaded_by": uploader,
                    "status": DocumentStatus.EXTRACTING,
                    "citation": opts["citation"],
                    "source_date": opts["source_date"],
                    "review_status": DocReviewStatus.UNREVIEWED,
                },
            )
            self.stdout.write(
                ("created Document " if doc_created else "reusing Document ")
                + f"id={doc.id} ({doc.filename})"
            )
            run = IngestRun.objects.create(
                source_document=doc,
                ingested_by=uploader,
                model_propose=settings.LLM_INGEST_PROPOSE_MODEL,
                model_audit=settings.LLM_INGEST_AUDIT_MODEL,
                model_compose=settings.LLM_INGEST_COMPOSE_MODEL,
                status=IngestRunStatus.RUNNING,
            )

        # Run the LLM passes outside the transaction so a long ingest does not
        # hold a write lock; persist results in a second short transaction.
        try:
            text = extract_text(source_path)
        except Exception as e:
            self._mark_failed(doc, run, f"extraction failed: {e}")
            raise CommandError(f"extraction failed: {e}") from e

        if not text.strip():
            self._mark_failed(doc, run, "extraction produced empty text")
            raise CommandError("extraction produced empty text")

        try:
            result = run_ingest(
                text,
                page_title=f"{case_template.title} — {opts['wiki_page_path']}",
                page_topic=opts["wiki_page_path"],
            )
        except ProviderConfigurationError as e:
            self._mark_failed(doc, run, str(e))
            raise CommandError(str(e)) from e
        except Exception as e:
            self._mark_failed(doc, run, f"LLM call failed: {e}")
            raise CommandError(f"LLM call failed: {e}") from e

        verdict_by_claim = {v.claim_id: v for v in result.verdicts}

        with transaction.atomic():
            wiki_page, page_created = WikiPage.objects.get_or_create(
                case_template=case_template,
                path=opts["wiki_page_path"],
                defaults={
                    "title": f"{case_template.title} — {opts['wiki_page_path']}",
                    "status": WikiPageStatus.DRAFT,
                    "content": result.page_markdown,
                },
            )
            if not page_created and result.page_markdown:
                # Faculty has reviewed the existing prose; overwrite only if there
                # is fresh material. We append a section divider so the prior
                # version can be eyeballed in the admin diff.
                wiki_page.content = (
                    f"{result.page_markdown}\n\n"
                    f"<!-- prior content (pre-ingest #{run.id}):\n{wiki_page.content}\n-->"
                    if wiki_page.content.strip()
                    else result.page_markdown
                )
                wiki_page.save(update_fields=["content"])
            wiki_page.source_documents.add(doc)
            run.wiki_pages.add(wiki_page)

            written = 0
            updated = 0
            for proposed in result.proposed:
                verdict = verdict_by_claim.get(proposed.claim_id)
                audit_status = ClaimAuditStatus.PROPOSED
                audit_notes = ""
                if verdict is not None:
                    audit_status = VERDICT_TO_STATUS.get(
                        verdict.verdict, ClaimAuditStatus.AUDITED_WEAK
                    )
                    audit_notes = f"[{verdict.verdict}] {verdict.rationale}"
                locator = {**proposed.source_locator, "evidence_grade": proposed.evidence_grade}
                _, created = Claim.objects.update_or_create(
                    wiki_page=wiki_page,
                    claim_id=proposed.claim_id,
                    defaults={
                        "statement": proposed.statement,
                        "source_document": doc,
                        "source_quote": proposed.source_quote,
                        "source_locator": locator,
                        "audit_status": audit_status,
                        "audit_notes": audit_notes,
                    },
                )
                written += 1
                if not created:
                    updated += 1

            doc.status = DocumentStatus.EXTRACTED
            doc.extracted_text_path = ""  # text held in claims, not persisted to disk yet
            doc.save(update_fields=["status", "extracted_text_path"])

            ok = sum(1 for v in result.verdicts if v.verdict == "ok")
            weak = sum(1 for v in result.verdicts if v.verdict == "weak")
            unsup = sum(1 for v in result.verdicts if v.verdict == "unsupported")
            run.propose_tokens_in = result.propose_tokens_in
            run.propose_tokens_out = result.propose_tokens_out
            run.audit_tokens_in = result.audit_tokens_in
            run.audit_tokens_out = result.audit_tokens_out
            run.compose_tokens_in = result.compose_tokens_in
            run.compose_tokens_out = result.compose_tokens_out
            run.cost_usd = Decimal(f"{result.total_cost_usd:.4f}")
            run.claims_proposed = len(result.proposed)
            run.claims_audited_ok = ok
            run.claims_audited_weak = weak + unsup
            run.claims_created = written - updated
            run.claims_updated = updated
            run.status = IngestRunStatus.COMPLETED
            run.completed_at = timezone.now()
            run.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Ingested {written} claims (propose ${result.propose_cost_usd:.4f} + "
                f"audit ${result.audit_cost_usd:.4f} + "
                f"compose ${result.compose_cost_usd:.4f} = ${result.total_cost_usd:.4f})"
            )
        )
        self.stdout.write(
            f"  audit verdicts: ok={ok} weak={weak} unsupported={unsup}; "
            f"page prose: {len(result.page_markdown)} chars"
        )
        self.stdout.write(
            f"  IngestRun #{run.id} logged. Review WikiPage prose + claims in admin; "
            f"set audit_status=published before they are citable."
        )

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _mime(self, path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }.get(suffix, "application/octet-stream")

    def _check_monthly_budget(self, *, force: bool) -> None:
        # The budget check is intentionally minimal in Phase A: we just warn
        # because we do not yet persist ingest cost rows. Phase B telemetry
        # will record per-ingest spend and turn this into a hard check.
        envelope = settings.INGEST_MONTHLY_BUDGET_USD
        if not force:
            self.stdout.write(
                f"(note: month-to-date ingest spend is not yet tracked; envelope is "
                f"${envelope:.2f}. Pass --force to suppress this notice once "
                f"telemetry lands in Phase B.)"
            )

    def _mark_failed(self, doc: Document, run: "IngestRun", reason: str) -> None:
        doc.status = DocumentStatus.FAILED
        doc.error_message = reason
        doc.save(update_fields=["status", "error_message"])
        run.status = IngestRunStatus.FAILED
        run.error_message = reason
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error_message", "completed_at"])
