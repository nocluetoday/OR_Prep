from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class DocumentStatus(models.TextChoices):
    UPLOADED = "uploaded", "Uploaded"
    EXTRACTING = "extracting", "Extracting"
    EXTRACTED = "extracted", "Extracted"
    FAILED = "failed", "Failed"


class Document(models.Model):
    """A raw source file uploaded by faculty/admin and attached to a module.

    The actual upload flow + extraction worker land in Phase A/B. This stub
    just defines the schema so the briefing pipeline has somewhere to write to.
    """

    module = models.ForeignKey(
        "modules.Module",
        on_delete=models.CASCADE,
        related_name="documents",
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

    history = HistoricalRecords()

    class Meta:
        unique_together = (("module", "sha256"),)
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return f"{self.filename} ({self.module.module_id})"
