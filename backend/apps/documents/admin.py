from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Document


@admin.register(Document)
class DocumentAdmin(SimpleHistoryAdmin):
    list_display = ("filename", "module", "status", "size_bytes", "uploaded_by", "uploaded_at")
    list_filter = ("status", "module__curriculum")
    search_fields = ("filename", "sha256", "module__module_id")
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
