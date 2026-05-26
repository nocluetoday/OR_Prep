from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class ReviewStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class CaseTemplate(models.Model):
    """A briefing skeleton for one procedural case type.

    Authored by faculty (Don for the PoC). The briefing generator loads exactly one
    CaseTemplate per request (resolved by `case_type` slug) plus any matching
    SurgeonPreference rows. Structured fields are JSON so the LLM reads them as a
    recipe rather than the app querying into them.
    """

    case_type = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    specialty = models.CharField(max_length=64, default="urology", db_index=True)
    summary = models.TextField(blank=True)

    # Structured shape consumed by the LLM. Each entry is a small dict; the
    # exact schema is documented in docs/journal.md and may evolve in Phase A.
    anatomy_focus = models.JSONField(default=list, blank=True)
    decision_points = models.JSONField(default=list, blank=True)
    complication_patterns = models.JSONField(default=list, blank=True)
    attending_question_categories = models.JSONField(default=list, blank=True)

    # Input form metadata: which patient factors this case type wants the
    # resident to fill in, with hints.
    patient_factor_fields = models.JSONField(default=list, blank=True)

    review_status = models.CharField(
        max_length=32,
        choices=ReviewStatus.choices,
        default=ReviewStatus.DRAFT,
    )
    version = models.CharField(max_length=32, default="0.0.0")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_case_templates",
    )
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ("specialty", "case_type")

    def __str__(self) -> str:
        return f"{self.title} ({self.case_type})"


class SurgeonPreference(models.Model):
    """One attending surgeon's documented preferences for one case type.

    Per the scope doc: surgeon preferences are opt-in per attending. The PoC ships
    with Don's HoLEP preferences; other attendings can be added later if they consent.
    Each preference item carries its own attribution (often "personal preference,
    documented YYYY-MM-DD" rather than a literature citation).
    """

    case_template = models.ForeignKey(
        CaseTemplate,
        on_delete=models.CASCADE,
        related_name="surgeon_preferences",
    )
    surgeon = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="surgeon_preferences",
    )

    # List of {id, label, statement, source} entries.
    preferences = models.JSONField(default=list, blank=True)

    review_status = models.CharField(
        max_length=32,
        choices=ReviewStatus.choices,
        default=ReviewStatus.DRAFT,
    )
    version = models.CharField(max_length=32, default="0.0.0")
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = (("case_template", "surgeon"),)
        ordering = ("case_template", "surgeon")

    def __str__(self) -> str:
        return f"{self.surgeon} / {self.case_template.case_type}"
