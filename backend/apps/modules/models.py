from django.db import models
from simple_history.models import HistoricalRecords


class ModuleType(models.TextChoices):
    CLINICAL_REASONING = "clinical_reasoning", "Clinical reasoning"
    ETHICS = "ethics", "Ethics"
    BOARD_REVIEW = "board_review", "Board review"
    PROCEDURAL = "procedural", "Procedural"
    COMMUNICATION = "communication", "Communication"
    MIXED = "mixed", "Mixed"


class ModuleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    FACULTY_REVIEWED = "faculty_reviewed", "Faculty reviewed"
    PILOT_READY = "pilot_ready", "Pilot ready"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class ObjectiveDomain(models.TextChoices):
    KNOWLEDGE = "knowledge", "Knowledge"
    REASONING = "reasoning", "Reasoning"
    COMMUNICATION = "communication", "Communication"
    ETHICS = "ethics", "Ethics"
    PROCEDURAL = "procedural", "Procedural"


class Module(models.Model):
    """A single topic module — the curriculum/case schema fed to the briefing generator.

    Cases / activities / remediation paths live as JSON because they're read
    as structured content by the LLM, not queried by the app. Learning
    objectives, knowledge checks, and references are normal child tables so
    future scoring and faculty workflows can join against them.
    """

    module_id = models.SlugField(max_length=128, unique=True)
    title = models.CharField(max_length=255)
    curriculum = models.CharField(max_length=64, db_index=True)
    specialty = models.CharField(max_length=64, blank=True, db_index=True)
    learner_level = models.CharField(max_length=64, blank=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    module_type = models.CharField(max_length=32, choices=ModuleType.choices, default=ModuleType.MIXED)
    status = models.CharField(max_length=32, choices=ModuleStatus.choices, default=ModuleStatus.DRAFT)
    version = models.CharField(max_length=32, default="0.0.0")
    source_version_date = models.CharField(max_length=64, blank=True)

    # Structured content the LLM reads but the app does not query into.
    activities = models.JSONField(default=list, blank=True)
    cases = models.JSONField(default=list, blank=True)
    remediation_paths = models.JSONField(default=list, blank=True)
    faculty_review = models.JSONField(default=dict, blank=True)

    # Where this row was imported from, relative to the project root.
    yaml_path = models.CharField(max_length=512, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ("curriculum", "title")

    def __str__(self) -> str:
        return f"{self.title} ({self.module_id})"


class LearningObjective(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="learning_objectives")
    objective_id = models.SlugField(max_length=128)
    text = models.TextField()
    domain = models.CharField(max_length=32, choices=ObjectiveDomain.choices, default=ObjectiveDomain.REASONING)

    history = HistoricalRecords()

    class Meta:
        unique_together = (("module", "objective_id"),)
        ordering = ("module", "objective_id")

    def __str__(self) -> str:
        return f"{self.module.module_id}:{self.objective_id}"


class KnowledgeCheck(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="knowledge_checks")
    check_id = models.SlugField(max_length=128)
    question = models.TextField()
    options = models.JSONField(default=list)  # list of {id, text}
    correct_option_id = models.CharField(max_length=32)
    explanation = models.TextField(blank=True)
    objectives = models.ManyToManyField(
        LearningObjective,
        related_name="knowledge_checks",
        blank=True,
    )

    history = HistoricalRecords()

    class Meta:
        unique_together = (("module", "check_id"),)
        ordering = ("module", "check_id")

    def __str__(self) -> str:
        return f"{self.module.module_id}:{self.check_id}"


class Reference(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="references")
    ref_id = models.SlugField(max_length=128)
    title = models.TextField()
    url = models.CharField(max_length=512, blank=True)
    version_date = models.CharField(max_length=64, blank=True)
    approved_by = models.CharField(max_length=128, blank=True)

    history = HistoricalRecords()

    class Meta:
        unique_together = (("module", "ref_id"),)
        ordering = ("module", "ref_id")

    def __str__(self) -> str:
        return f"{self.module.module_id}:{self.ref_id}"
