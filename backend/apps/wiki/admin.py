from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from simple_history.admin import SimpleHistoryAdmin

from .forms import LLMSettingsForm
from .models import Claim, IngestRun, LLMSettings, WikiPage


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


@admin.register(LLMSettings)
class LLMSettingsAdmin(SimpleHistoryAdmin):
    """Singleton admin: one row, write-only API key fields, redirected from the
    changelist straight to the edit page."""

    form = LLMSettingsForm
    readonly_fields = ("updated_at", "updated_by")
    fieldsets = (
        (
            "Briefing stage",
            {
                "fields": ("briefing_provider", "briefing_model"),
                "description": (
                    "Per-CaseTemplate overrides take precedence over these. "
                    "Leave blank to fall through to env LLM_BRIEFING_*."
                ),
            },
        ),
        (
            "Ingest stages",
            {
                "fields": (
                    "ingest_propose_provider",
                    "ingest_propose_model",
                    "ingest_audit_provider",
                    "ingest_audit_model",
                    "ingest_compose_provider",
                    "ingest_compose_model",
                ),
                "description": (
                    "Mix providers across stages — e.g. local LM Studio for "
                    "propose (cheap), Anthropic Opus for audit (strict)."
                ),
            },
        ),
        (
            "API keys",
            {
                "fields": (
                    "anthropic_api_key",
                    "openai_api_key",
                    "openrouter_api_key",
                    "lmstudio_api_key",
                ),
                "description": (
                    "Encrypted at rest with a Fernet key derived from "
                    "DJANGO_SECRET_KEY. Rotating SECRET_KEY invalidates "
                    "stored keys — re-enter them after a rotation. Fields "
                    "are write-only: existing values are never displayed."
                ),
            },
        ),
        (
            "Base URLs",
            {
                "fields": ("openai_base_url", "lmstudio_base_url", "openrouter_base_url"),
                "description": (
                    "Override the default API endpoint per provider. Blank "
                    "uses the provider default (e.g. LM Studio defaults to "
                    "http://localhost:1234/v1)."
                ),
            },
        ),
        ("Provenance", {"fields": ("updated_at", "updated_by")}),
    )

    def has_add_permission(self, request):
        # Singleton: only allow creation if no row exists yet. Even then the
        # changelist redirect below normally creates the row on first visit.
        return not LLMSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Skip the list view and land on the singleton's edit page directly.
        obj = LLMSettings.get_singleton()
        return HttpResponseRedirect(
            reverse("admin:wiki_llmsettings_change", args=(obj.pk,))
        )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


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
