from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import WikiPage


@admin.register(WikiPage)
class WikiPageAdmin(SimpleHistoryAdmin):
    list_display = ("module", "path", "title", "status", "approved_by", "updated_at")
    list_filter = ("status", "module__curriculum")
    search_fields = ("path", "title", "module__module_id")
    readonly_fields = ("created_at", "updated_at", "approved_at")
    filter_horizontal = ("source_documents",)
