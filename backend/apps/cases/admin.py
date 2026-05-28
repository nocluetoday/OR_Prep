from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import CaseTemplate, SurgeonPreference


@admin.register(CaseTemplate)
class CaseTemplateAdmin(SimpleHistoryAdmin):
    list_display = (
        "case_type",
        "title",
        "specialty",
        "review_status",
        "version",
        "last_reviewed_at",
        "updated_at",
    )
    list_filter = ("specialty", "review_status")
    search_fields = ("case_type", "title")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("case_type", "title", "specialty", "summary")}),
        (
            "Briefing shape (LLM context)",
            {
                "fields": (
                    "anatomy_focus",
                    "decision_points",
                    "complication_patterns",
                    "attending_question_categories",
                    "input_schema",
                ),
            },
        ),
        (
            "Review",
            {
                "fields": (
                    "review_status",
                    "version",
                    "reviewed_by",
                    "last_reviewed_at",
                ),
            },
        ),
        (
            "Briefing provider override (optional)",
            {
                "fields": ("briefing_provider_override", "briefing_model_override"),
                "description": (
                    "If both fields are left blank, the briefing CLI uses "
                    "LLM_BRIEFING_PROVIDER and LLM_BRIEFING_MODEL from settings. "
                    "Set these to pin a specific backend for this case (e.g. "
                    "anthropic + claude-sonnet-4-6 for high-stakes cases)."
                ),
            },
        ),
        ("Provenance", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(SurgeonPreference)
class SurgeonPreferenceAdmin(SimpleHistoryAdmin):
    list_display = (
        "surgeon",
        "case_template",
        "review_status",
        "version",
        "last_reviewed_at",
        "updated_at",
    )
    list_filter = ("review_status", "case_template__case_type")
    search_fields = ("surgeon__email", "case_template__case_type")
    readonly_fields = ("created_at", "updated_at")
