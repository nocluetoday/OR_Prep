"""Forms for apps.wiki admin.

The `LLMSettingsForm` handles the secret-key UX: the model stores encrypted
ciphertext, but the admin form is write-only. Each key field renders as an
empty PasswordInput with "leave blank to keep" help text. On save, any field
the user typed into is encrypted and persisted; blank fields leave the
existing value untouched.
"""

from __future__ import annotations

from django import forms

from .models import LLMSettings


_PROVIDER_CHOICES = (
    ("", "(use env LLM_*_PROVIDER)"),
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("lmstudio", "LM Studio (local)"),
    ("openrouter", "OpenRouter"),
)


class LLMSettingsForm(forms.ModelForm):
    briefing_provider = forms.ChoiceField(choices=_PROVIDER_CHOICES, required=False)
    ingest_propose_provider = forms.ChoiceField(choices=_PROVIDER_CHOICES, required=False)
    ingest_audit_provider = forms.ChoiceField(choices=_PROVIDER_CHOICES, required=False)
    ingest_compose_provider = forms.ChoiceField(choices=_PROVIDER_CHOICES, required=False)

    anthropic_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Encrypted at rest. Leave blank to keep the existing value.",
        label="Anthropic API key",
    )
    openai_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Encrypted at rest. Leave blank to keep the existing value.",
        label="OpenAI API key",
    )
    openrouter_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text="Encrypted at rest. Leave blank to keep the existing value.",
        label="OpenRouter API key",
    )
    lmstudio_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=(
            "Encrypted at rest. LM Studio accepts any non-empty string; the "
            "sentinel 'lm-studio' is used when this and env are both blank. "
            "Leave blank to keep the existing value."
        ),
        label="LM Studio API key",
    )

    class Meta:
        model = LLMSettings
        # Encrypted ciphertext fields are managed via the password fields above;
        # don't expose them directly in the form.
        exclude = (
            "anthropic_api_key_enc",
            "openai_api_key_enc",
            "openrouter_api_key_enc",
            "lmstudio_api_key_enc",
        )

    def save(self, commit=True):
        instance: LLMSettings = super().save(commit=False)
        for provider in ("anthropic", "openai", "openrouter", "lmstudio"):
            typed = (self.cleaned_data.get(f"{provider}_api_key") or "").strip()
            if typed:
                instance.set_api_key(provider, typed)
        if commit:
            instance.save()
        return instance
