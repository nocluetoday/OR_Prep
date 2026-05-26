from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class DocumentStatus(models.TextChoices):
    UPLOADED = "uploaded", "Uploaded"
    EXTRACTING = "extracting", "Extracting"
    EXTRACTED = "extracted", "Extracted"
    FAILED = "failed", "Failed"


class ReviewStatus(models.TextChoices):
    """Faculty review state of the source itself, separate from extraction status."""

    UNREVIEWED = "unreviewed", "Unreviewed"
    PUBLISHED = "published", "Published (claims may be cited)"
    ARCHIVED = "archived", "Archived (not citable)"


class Document(models.Model):
    """A raw source file uploaded by faculty/admin.

    May be attached to a curriculum Module (legacy) or a CaseTemplate (Phase A
    onward). The briefing surface in `apps.cases` only reads Documents reachable
    through Claims attached to published WikiPages of a CaseTemplate.
    """

    module = models.ForeignKey(
        "modules.Module",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    case_template = models.ForeignKey(
        "cases.CaseTemplate",
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    filename = models.CharField(max_length=512)
    mime_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    raw_path = models.CharField(max_length=512)
    extracted_text_path = models.CharField(max_length=512, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=32,
        choices=DocumentStatus.choices,
        default=DocumentStatus.UPLOADED,
    )
    error_message = models.TextField(blank=True)

    # Source freshness — the briefing renderer surfaces these so the resident
    # can see "most recent review: 2024-08" alongside cited claims.
    source_date = models.CharField(
        max_length=64,
        blank=True,
        help_text="Publication / version date of the source (free-form: YYYY, YYYY-MM, YYYY-MM-DD).",
    )
    citation = models.TextField(
        blank=True,
        help_text="Human-readable citation string (author, title, journal/publisher, year).",
    )
    review_status = models.CharField(
        max_length=32,
        choices=ReviewStatus.choices,
        default=ReviewStatus.UNREVIEWED,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_documents",
    )
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ("-uploaded_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("module", "sha256"),
                name="documents_unique_module_sha",
                condition=models.Q(module__isnull=False),
            ),
            models.UniqueConstraint(
                fields=("case_template", "sha256"),
                name="documents_unique_case_template_sha",
                condition=models.Q(case_template__isnull=False),
            ),
            models.CheckConstraint(
                check=(
                    models.Q(module__isnull=False, case_template__isnull=True)
                    | models.Q(module__isnull=True, case_template__isnull=False)
                ),
                name="documents_one_parent_only",
            ),
        ]

    def __str__(self) -> str:
        if self.case_template_id:
            return f"{self.filename} ({self.case_template.case_type})"
        if self.module_id:
            return f"{self.filename} ({self.module.module_id})"
        return self.filename
