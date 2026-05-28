"""Import faculty-authored case-template YAML files into the DB.

Reads `modules/cases/**/case_template.yaml` (skipping any path containing
`_template`), upserts each `CaseTemplate` by its `case_type` slug, validates
the `input_schema` block strictly, and reports created / updated / unchanged
counts. Mirrors the legacy `apps.modules.management.commands.import_modules`
shape so authors hit one mental model for both.

Validation rules enforced here (failures exit non-zero with clear stderr):
- `case_type` is required and must be a slug
- `input_schema` is a dict with both `quick` and `expanded` lists
- each field has `name` / `label` / `type` in the allowed set
- `select` / `multi_select` carry a non-empty `options` list of `{value, label}`
- field `name`s are unique across `quick + expanded` in a single file (the
  resident's submitted values merge into one flat dict; collisions would
  silently overwrite)

No surgeon-preference handling: SurgeonPreference is admin-only because its
authorship is attributable to a specific user.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cases.models import CaseTemplate


ALLOWED_TYPES = frozenset({"select", "text", "number", "boolean", "multi_select"})
ALLOWED_REVIEW_STATUS = frozenset({"draft", "published", "archived"})
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_\-]*$")


class Command(BaseCommand):
    help = "Import faculty-authored case-template YAML files into the DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            help="Override MODULES_DIR for this run (absolute path).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the DB.",
        )

    def handle(self, *args, **options):
        modules_dir = Path(options.get("path") or settings.MODULES_DIR).resolve()
        if not modules_dir.exists():
            raise CommandError(f"modules dir not found: {modules_dir}")

        yaml_files = sorted(
            p
            for p in modules_dir.rglob("case_template.yaml")
            if "_template" not in p.parts
        )
        if not yaml_files:
            self.stdout.write(
                self.style.WARNING(
                    f"No case_template.yaml files found under {modules_dir}"
                )
            )
            return

        dry_run = options["dry_run"]
        created = updated = unchanged = 0
        had_errors = False

        for yaml_path in yaml_files:
            try:
                data = yaml.safe_load(yaml_path.read_text())
            except yaml.YAMLError as e:
                had_errors = True
                self.stderr.write(self.style.ERROR(f"YAML parse failed: {yaml_path}: {e}"))
                continue

            rel_path = self._relative_path(yaml_path, modules_dir)

            try:
                self._validate(data, rel_path)
            except CommandError as e:
                had_errors = True
                self.stderr.write(self.style.ERROR(f"Validation failed: {rel_path}: {e}"))
                continue

            if dry_run:
                self.stdout.write(f"[dry-run] would import {data['case_type']} from {rel_path}")
                continue

            try:
                with transaction.atomic():
                    result = self._upsert_case_template(data)
            except Exception as e:
                had_errors = True
                self.stderr.write(
                    self.style.ERROR(f"Import failed for {data['case_type']}: {e}")
                )
                continue

            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                unchanged += 1
            self.stdout.write(f"  {result}: {data['case_type']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} updated={updated} unchanged={unchanged}"
            )
        )

        if had_errors:
            # Non-zero exit so CI / scripted authoring catches the failure.
            raise CommandError("one or more case templates failed validation or import")

    # ------------------------------------------------------------------ helpers

    def _relative_path(self, yaml_path: Path, modules_dir: Path) -> str:
        try:
            return str(Path("modules") / yaml_path.relative_to(modules_dir))
        except ValueError:
            return str(yaml_path)

    def _validate(self, data: object, rel_path: str) -> None:
        if not isinstance(data, dict):
            raise CommandError("top-level YAML must be a mapping")

        case_type = data.get("case_type")
        if not case_type or not isinstance(case_type, str) or not _SLUG_RE.match(case_type):
            raise CommandError(
                f"case_type must be a snake_case / kebab-case slug; got {case_type!r}"
            )

        review_status = data.get("review_status", "draft")
        if review_status not in ALLOWED_REVIEW_STATUS:
            raise CommandError(
                f"review_status must be one of {sorted(ALLOWED_REVIEW_STATUS)}; got {review_status!r}"
            )

        input_schema = data.get("input_schema")
        if not isinstance(input_schema, dict):
            raise CommandError("input_schema must be a mapping with 'quick' and 'expanded' lists")

        seen_names: set[str] = set()
        for group in ("quick", "expanded"):
            fields = input_schema.get(group)
            if not isinstance(fields, list):
                raise CommandError(f"input_schema.{group} must be a list")
            for idx, field in enumerate(fields):
                self._validate_field(field, where=f"input_schema.{group}[{idx}]")
                name = field["name"]
                if name in seen_names:
                    raise CommandError(
                        f"duplicate field name {name!r} across input_schema.quick + expanded "
                        f"(field names submit into a flat dict; must be unique)"
                    )
                seen_names.add(name)

    def _validate_field(self, field: object, *, where: str) -> None:
        if not isinstance(field, dict):
            raise CommandError(f"{where}: must be a mapping")
        name = field.get("name")
        if not isinstance(name, str) or not _SLUG_RE.match(name):
            raise CommandError(f"{where}: name must be a snake_case / kebab-case slug; got {name!r}")
        label = field.get("label")
        if not isinstance(label, str) or not label.strip():
            raise CommandError(f"{where}: label must be a non-empty string")
        field_type = field.get("type")
        if field_type not in ALLOWED_TYPES:
            raise CommandError(
                f"{where}: type must be one of {sorted(ALLOWED_TYPES)}; got {field_type!r}"
            )
        if field_type in ("select", "multi_select"):
            options = field.get("options")
            if not isinstance(options, list) or not options:
                raise CommandError(
                    f"{where}: options must be a non-empty list for {field_type}"
                )
            for opt_idx, opt in enumerate(options):
                if not isinstance(opt, dict):
                    raise CommandError(f"{where}.options[{opt_idx}]: must be a mapping")
                if not isinstance(opt.get("value"), str) or not opt["value"]:
                    raise CommandError(f"{where}.options[{opt_idx}]: value must be a non-empty string")
                if not isinstance(opt.get("label"), str) or not opt["label"]:
                    raise CommandError(f"{where}.options[{opt_idx}]: label must be a non-empty string")
        # `required` is optional and defaults to false; `help_text` is optional.

    def _upsert_case_template(self, data: dict) -> str:
        defaults = {
            "title": str(data.get("title") or "").strip(),
            "specialty": str(data.get("specialty") or "urology").strip(),
            "summary": str(data.get("summary") or ""),
            "anatomy_focus": data.get("anatomy_focus") or [],
            "decision_points": data.get("decision_points") or [],
            "complication_patterns": data.get("complication_patterns") or [],
            "attending_question_categories": data.get("attending_question_categories") or [],
            "input_schema": data.get("input_schema") or {"quick": [], "expanded": []},
            "review_status": data.get("review_status", "draft"),
            "version": str(data.get("version") or "0.0.0"),
        }
        # Capture the pre-write snapshot BEFORE the upsert. We compare against
        # this to distinguish "updated" (real diff) from "unchanged" (idempotent
        # re-import). Do not "simplify" by reusing update_or_create's return
        # value — that's the post-write instance and would always report
        # unchanged for an existing row.
        existing = CaseTemplate.objects.filter(case_type=data["case_type"]).first()
        case_template, created = CaseTemplate.objects.update_or_create(
            case_type=data["case_type"],
            defaults=defaults,
        )
        if created:
            return "created"
        if existing is None:
            return "updated"
        for key, value in defaults.items():
            if getattr(existing, key) != value:
                return "updated"
        return "unchanged"
