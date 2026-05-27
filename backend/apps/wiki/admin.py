from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Claim, IngestRun, WikiPage


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


@admin.register(IngestRun)
class IngestRunAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "source_document",
        "ingested_by",
        "status",
        "claims_created",
        "claims_audited_ok",
        "claims_audited_weak",
        "cost_usd",
        "started_at",
    )
    list_filter = ("status", "model_propose", "model_audit", "model_compose")
    search_fields = ("source_document__filename", "ingested_by__email")
    readonly_fields = (
        "source_document",
        "ingested_by",
        "wiki_pages",
        "model_propose",
        "model_audit",
        "model_compose",
        "propose_tokens_in",
        "propose_tokens_out",
        "audit_tokens_in",
        "audit_tokens_out",
        "compose_tokens_in",
        "compose_tokens_out",
        "cost_usd",
        "claims_proposed",
        "claims_audited_ok",
        "claims_audited_weak",
        "claims_created",
        "claims_updated",
        "status",
        "error_message",
        "started_at",
        "completed_at",
    )


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
