from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class WikiPageStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class WikiPage(models.Model):
    """One LLM-curated knowledge page, attached to a module.

    Status is page-level — faculty approves or rejects per page. The briefing generator
    reads only `published` pages. Content history is captured via
    HistoricalRecords so we can diff and roll back without separate
    versioning tables.
    """

    module = models.ForeignKey(
        "modules.Module",
        on_delete=models.CASCADE,
        related_name="wiki_pages",
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
        unique_together = (("module", "path"),)
        ordering = ("module", "path")

    def __str__(self) -> str:
        return f"{self.module.module_id}:{self.path}"
