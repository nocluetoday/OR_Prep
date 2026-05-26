from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Document


@admin.register(Document)
class DocumentAdmin(SimpleHistoryAdmin):
    list_display = (
        "filename",
        "case_template",
        "module",
        "review_status",
        "source_date",
        "status",
        "uploaded_at",
    )
    list_filter = ("review_status", "status", "case_template__case_type", "module__curriculum")
    search_fields = ("filename", "sha256", "citation", "case_template__case_type", "module__module_id")
    readonly_fields = (
        "filename",
        "mime_type",
        "size_bytes",
        "sha256",
        "raw_path",
        "extracted_text_path",
        "uploaded_by",
        "uploaded_at",
    )
    fieldsets = (
        (None, {"fields": ("module", "case_template", "filename", "citation")}),
        (
            "Source freshness",
            {"fields": ("source_date", "review_status", "reviewed_by", "last_reviewed_at")},
        ),
        (
            "File metadata",
            {
                "fields": (
                    "mime_type",
                    "size_bytes",
                    "sha256",
                    "raw_path",
                    "extracted_text_path",
                ),
            },
        ),
        (
            "Extraction state",
            {"fields": ("status", "error_message")},
        ),
        ("Provenance", {"fields": ("uploaded_by", "uploaded_at")}),
    )
