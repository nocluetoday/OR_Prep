"""Generate a structured case-prep briefing for a urology resident.

Usage:
  python manage.py generate_briefing \\
      --case holep \\
      --factors 'prostate_volume_g=80,anticoagulation=warfarin,indication=retention' \\
      --surgeon neff@example.com \\
      --time 10 \\
      --focus 'large median lobe, worried about apex dissection'

The command:
  1. Resolves the CaseTemplate by case_type slug.
  2. Loads SurgeonPreference (all matching surgeon_email, if provided).
  3. Calls the briefing service, which runs a tool-use loop where the LLM must
     call `cite(claim_id)` for every factual claim. Server-side validation
     drops/flags unsupported cites and pins each valid one to the WikiPage's
     current history_id.
  4. Prints the rendered markdown briefing to stdout. Phase B will persist
     this as a Telemetry row.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.cases.models import CaseTemplate, SurgeonPreference
from apps.cases.services.briefing import generate_briefing
from apps.wiki.services.providers import ProviderConfigurationError


class Command(BaseCommand):
    help = "Generate a procedural case-prep briefing for one resident request."

    def add_arguments(self, parser):
        parser.add_argument("--case", required=True, help="CaseTemplate.case_type slug.")
        parser.add_argument(
            "--factors",
            default="",
            help="Comma-separated key=value patient factors (e.g. 'prostate_volume_g=80,anticoagulation=warfarin').",
        )
        parser.add_argument(
            "--surgeon",
            default="",
            help="Email of the attending surgeon (matches SurgeonPreference.surgeon.email).",
        )
        parser.add_argument(
            "--time",
            type=int,
            choices=(5, 10, 20),
            default=10,
            help="Time budget in minutes (5 / 10 / 20).",
        )
        parser.add_argument(
            "--focus",
            default="",
            help="Free-text focus from the resident (one sentence).",
        )

    def handle(self, *args, **opts):
        try:
            case_template = CaseTemplate.objects.get(case_type=opts["case"])
        except CaseTemplate.DoesNotExist as e:
            raise CommandError(f"no CaseTemplate with case_type={opts['case']!r}") from e

        surgeon_email = opts["surgeon"].strip() or None
        surgeon_prefs: list[SurgeonPreference] = []
        if surgeon_email:
            User = get_user_model()
            try:
                surgeon = User.objects.get(email=surgeon_email)
            except User.DoesNotExist as e:
                raise CommandError(f"no user with email={surgeon_email!r}") from e
            surgeon_prefs = list(
                SurgeonPreference.objects.filter(
                    case_template=case_template, surgeon=surgeon
                )
            )

        factors = self._parse_factors(opts["factors"])

        try:
            result = generate_briefing(
                case_template=case_template,
                surgeon_preferences=surgeon_prefs,
                patient_factors=factors,
                surgeon_email=surgeon_email,
                time_minutes=opts["time"],
                focus_text=opts["focus"],
            )
        except ProviderConfigurationError as e:
            raise CommandError(str(e)) from e
        except Exception as e:
            raise CommandError(f"briefing generation failed: {e}") from e

        self.stdout.write(result.markdown)
        self.stdout.write("")
        cache_str = (
            f" (cached: {result.cached_tokens_in}↓)" if result.cached_tokens_in else ""
        )
        summary = (
            f"Briefing complete: {len(result.citations)} cited claims, "
            f"{len(result.rejected_cites)} rejected. "
            f"~{result.tokens_in}↓{cache_str} {result.tokens_out}↑ tokens, "
            f"~${result.cost_usd:.4f} ({result.provider}/{result.model})."
        )
        if result.no_tool_calls_warning:
            self.stderr.write(
                self.style.WARNING(
                    f"WARNING: {result.provider}/{result.model} did not call the "
                    "cite() tool for any statement. The briefing is unsupported. "
                    "Re-run with a tool-calling model."
                )
            )
            self.stdout.write(self.style.WARNING(summary))
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _parse_factors(self, raw: str) -> dict:
        if not raw.strip():
            return {}
        out: dict = {}
        for part in raw.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            out[key.strip()] = value.strip()
        return out
