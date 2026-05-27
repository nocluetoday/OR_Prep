from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class WikiPageStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class ClaimAuditStatus(models.TextChoices):
    """Lifecycle of a Claim through the ingest + audit pipeline.

    proposed → audit pass marks ok/weak → faculty reviews → published or rejected.
    The briefing's cite() tool only resolves PUBLISHED claims.
    """

    PROPOSED = "proposed", "Proposed (pre-audit)"
    AUDITED_OK = "audited_ok", "Audit OK"
    AUDITED_WEAK = "audited_weak", "Audit flagged weak"
    PUBLISHED = "published", "Published"
    REJECTED = "rejected", "Rejected"


class WikiPage(models.Model):
    """One LLM-curated knowledge page, attached to a module or case template.

    Status is page-level — faculty approves or rejects per page. The briefing generator
    reads only `published` pages. Content history is captured via
    HistoricalRecords so we can diff and roll back without separate
    versioning tables. Citations are version-pinned by storing the WikiPage's
    `history_id` at briefing-generation time so later edits do not silently
    invalidate prior briefings.
    """

    module = models.ForeignKey(
        "modules.Module",
        on_delete=models.CASCADE,
        related_name="wiki_pages",
        null=True,
        blank=True,
    )
    case_template = models.ForeignKey(
        "cases.CaseTemplate",
        on_delete=models.CASCADE,
        related_name="wiki_pages",
        null=True,
        blank=True,
    )
    path = models.CharField(max_length=512)
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=WikiPageStatus.choices,
        default=WikiPageStatus.DRAFT,
    )
    source_documents = models.ManyToManyField(
        "documents.Document",
        related_name="wiki_pages",
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_wiki_pages",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_wiki_pages",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ("path",)
        constraints = [
            models.UniqueConstraint(
                fields=("module", "path"),
                name="wiki_unique_module_path",
                condition=models.Q(module__isnull=False),
            ),
            models.UniqueConstraint(
                fields=("case_template", "path"),
                name="wiki_unique_case_template_path",
                condition=models.Q(case_template__isnull=False),
            ),
            models.CheckConstraint(
                check=(
                    models.Q(module__isnull=False, case_template__isnull=True)
                    | models.Q(module__isnull=True, case_template__isnull=False)
                ),
                name="wiki_one_parent_only",
            ),
        ]

    def __str__(self) -> str:
        owner = self.module.module_id if self.module_id else (
            self.case_template.case_type if self.case_template_id else "orphan"
        )
        return f"{owner}:{self.path}"


class IngestRunStatus(models.TextChoices):
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class IngestRun(models.Model):
    """One row per `ingest_document` invocation — the wiki's append-only log.

    Per the Karpathy LLM-wiki model (gist 442a6bf...), every ingest appends a
    log entry. This is that log: which source produced which claims under
    which models, at what cost. Browsable in admin; treated as immutable after
    completion (the audit log on the model captures any later annotations).
    """

    source_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="ingest_runs",
    )
    ingested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ingest_runs",
    )
    wiki_pages = models.ManyToManyField(
        "wiki.WikiPage",
        related_name="ingest_runs",
        blank=True,
    )

    model_propose = models.CharField(max_length=64, blank=True)
    model_audit = models.CharField(max_length=64, blank=True)
    model_compose = models.CharField(max_length=64, blank=True)

    propose_tokens_in = models.IntegerField(default=0)
    propose_tokens_out = models.IntegerField(default=0)
    audit_tokens_in = models.IntegerField(default=0)
    audit_tokens_out = models.IntegerField(default=0)
    compose_tokens_in = models.IntegerField(default=0)
    compose_tokens_out = models.IntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)

    claims_proposed = models.IntegerField(default=0)
    claims_audited_ok = models.IntegerField(default=0)
    claims_audited_weak = models.IntegerField(default=0)
    claims_created = models.IntegerField(default=0)
    claims_updated = models.IntegerField(default=0)

    status = models.CharField(
        max_length=32,
        choices=IngestRunStatus.choices,
        default=IngestRunStatus.RUNNING,
    )
    error_message = models.TextField(blank=True)

    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"IngestRun #{self.id}: {self.source_document.filename}"

    @property
    def total_tokens_in(self) -> int:
        return self.propose_tokens_in + self.audit_tokens_in + self.compose_tokens_in

    @property
    def total_tokens_out(self) -> int:
        return self.propose_tokens_out + self.audit_tokens_out + self.compose_tokens_out


class Claim(models.Model):
    """A single factual statement extracted from a Document, attached to a WikiPage.

    Every claim in a briefing must resolve to a published Claim. The ingest pipeline
    proposes claims from extracted document text; the adversarial audit pass flags
    weak or unsupported attributions; faculty publishes the OK'd ones. The
    briefing's `cite(claim_id)` tool resolves the slug against this table, with a
    history pin so later edits do not silently invalidate prior briefings.
    """

    wiki_page = models.ForeignKey(
        WikiPage,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    claim_id = models.SlugField(max_length=128)
    statement = models.TextField()

    source_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.PROTECT,
        related_name="claims",
        null=True,
        blank=True,
        help_text=(
            "The source from which this claim was extracted. May be null for "
            "documented personal preferences (e.g., a surgeon's noted approach)."
        ),
    )
    source_quote = models.TextField(
        blank=True,
        help_text="Exact text span from the source supporting the statement.",
    )
    # JSON locator so source-type-specific addressing (page number for PDFs,
    # section for textbook chapters, timestamp for video) lives in one column.
    source_locator = models.JSONField(default=dict, blank=True)

    audit_status = models.CharField(
        max_length=32,
        choices=ClaimAuditStatus.choices,
        default=ClaimAuditStatus.PROPOSED,
    )
    audit_notes = models.TextField(
        blank=True,
        help_text="Adversarial-audit verdict and rationale (LLM- or faculty-written).",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_claims",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = (("wiki_page", "claim_id"),)
        ordering = ("wiki_page", "claim_id")

    def __str__(self) -> str:
        return f"{self.wiki_page}:{self.claim_id}"

    @property
    def is_publishable(self) -> bool:
        return self.audit_status in (
            ClaimAuditStatus.AUDITED_OK,
            ClaimAuditStatus.PUBLISHED,
        )
