from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Claim, WikiPage


class ClaimInline(admin.TabularInline):
    model = Claim
    extra = 0
    fields = ("claim_id", "statement", "source_document", "audit_status")
    show_change_link = True


@admin.register(WikiPage)
class WikiPageAdmin(SimpleHistoryAdmin):
    list_display = (
        "path",
        "title",
        "module",
        "case_template",
        "status",
        "approved_by",
        "updated_at",
    )
    list_filter = ("status", "module__curriculum", "case_template__case_type")
    search_fields = ("path", "title", "module__module_id", "case_template__case_type")
    readonly_fields = ("created_at", "updated_at", "approved_at")
    filter_horizontal = ("source_documents",)
    inlines = [ClaimInline]


@admin.register(Claim)
class ClaimAdmin(SimpleHistoryAdmin):
    list_display = (
        "claim_id",
        "wiki_page",
        "source_document",
        "audit_status",
        "reviewed_by",
        "updated_at",
    )
    list_filter = ("audit_status", "wiki_page__case_template__case_type")
    search_fields = ("claim_id", "statement", "source_quote")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("wiki_page", "claim_id", "statement")}),
        (
            "Source attribution",
            {"fields": ("source_document", "source_quote", "source_locator")},
        ),
        (
            "Audit + review",
            {
                "fields": (
                    "audit_status",
                    "audit_notes",
                    "reviewed_by",
                    "reviewed_at",
                ),
            },
        ),
        ("Provenance", {"fields": ("created_at", "updated_at")}),
    )
