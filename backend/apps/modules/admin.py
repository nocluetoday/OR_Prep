from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import KnowledgeCheck, LearningObjective, Module, Reference


class LearningObjectiveInline(admin.TabularInline):
    model = LearningObjective
    extra = 0
    fields = ("objective_id", "text", "domain")


class KnowledgeCheckInline(admin.TabularInline):
    model = KnowledgeCheck
    extra = 0
    fields = ("check_id", "question", "correct_option_id")
    show_change_link = True


class ReferenceInline(admin.TabularInline):
    model = Reference
    extra = 0
    fields = ("ref_id", "title", "url", "version_date", "approved_by")


@admin.register(Module)
class ModuleAdmin(SimpleHistoryAdmin):
    list_display = ("module_id", "title", "curriculum", "status", "version", "learner_level", "updated_at")
    list_filter = ("curriculum", "status", "module_type")
    search_fields = ("module_id", "title", "specialty")
    readonly_fields = ("yaml_path", "created_at", "updated_at")
    inlines = [LearningObjectiveInline, ReferenceInline, KnowledgeCheckInline]
    fieldsets = (
        (None, {"fields": ("module_id", "title", "curriculum", "specialty", "learner_level")}),
        ("Module shape", {"fields": ("module_type", "estimated_minutes", "version", "source_version_date", "status")}),
        ("Structured content (read by the LLM)", {"fields": ("activities", "cases", "remediation_paths", "faculty_review")}),
        ("Provenance", {"fields": ("yaml_path", "created_at", "updated_at")}),
    )


@admin.register(LearningObjective)
class LearningObjectiveAdmin(SimpleHistoryAdmin):
    list_display = ("module", "objective_id", "domain", "text")
    list_filter = ("domain", "module__curriculum")
    search_fields = ("objective_id", "text")


@admin.register(KnowledgeCheck)
class KnowledgeCheckAdmin(SimpleHistoryAdmin):
    list_display = ("module", "check_id", "question", "correct_option_id")
    list_filter = ("module__curriculum",)
    search_fields = ("check_id", "question")
    filter_horizontal = ("objectives",)


@admin.register(Reference)
class ReferenceAdmin(SimpleHistoryAdmin):
    list_display = ("module", "ref_id", "title", "approved_by")
    list_filter = ("module__curriculum",)
    search_fields = ("ref_id", "title")
