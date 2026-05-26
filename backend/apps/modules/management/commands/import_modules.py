"""Import faculty-authored module YAML files into the DB.

Reads `modules/**/module.yaml` (skipping `_template/`), upserts each Module by
its `module_id`, and syncs LearningObjective / KnowledgeCheck / Reference
children. JSON-shaped content (activities, cases, remediation_paths,
faculty_review) is written verbatim to JSONField columns.

The command is idempotent: running twice with no YAML changes produces no
DB writes (beyond simple-history's normal accounting). Children no longer
present in the YAML are deleted.
"""

from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.modules.models import (
    KnowledgeCheck,
    LearningObjective,
    Module,
    Reference,
)


class Command(BaseCommand):
    help = "Import faculty-authored module YAML files into the DB."

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
            for p in modules_dir.rglob("module.yaml")
            if "_template" not in p.parts
        )
        if not yaml_files:
            self.stdout.write(self.style.WARNING(f"No module YAML files found under {modules_dir}"))
            return

        dry_run = options["dry_run"]
        created = updated = unchanged = 0

        for yaml_path in yaml_files:
            try:
                data = yaml.safe_load(yaml_path.read_text())
            except yaml.YAMLError as e:
                self.stderr.write(self.style.ERROR(f"YAML parse failed: {yaml_path}: {e}"))
                continue

            module_id = data.get("module_id")
            if not module_id:
                self.stderr.write(self.style.ERROR(f"Missing module_id: {yaml_path}"))
                continue

            rel_path = self._relative_path(yaml_path, modules_dir)

            if dry_run:
                self.stdout.write(f"[dry-run] would import {module_id} from {rel_path}")
                continue

            try:
                with transaction.atomic():
                    result = self._upsert_module(data, rel_path)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Import failed for {module_id}: {e}"))
                continue

            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                unchanged += 1
            self.stdout.write(f"  {result}: {module_id}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} updated={updated} unchanged={unchanged}"
            )
        )

    def _relative_path(self, yaml_path: Path, modules_dir: Path) -> str:
        try:
            return str(Path("modules") / yaml_path.relative_to(modules_dir))
        except ValueError:
            return str(yaml_path)

    def _upsert_module(self, data: dict, rel_path: str) -> str:
        module_fields = {
            "title": data.get("title", ""),
            "curriculum": data.get("curriculum", ""),
            "specialty": data.get("specialty", ""),
            "learner_level": data.get("learner_level", ""),
            "estimated_minutes": int(data.get("estimated_minutes") or 0),
            "module_type": data.get("module_type") or "mixed",
            "status": data.get("status") or "draft",
            "version": data.get("version") or "0.0.0",
            "source_version_date": str(data.get("source_version_date") or ""),
            "activities": data.get("activities") or [],
            "cases": data.get("cases") or [],
            "remediation_paths": data.get("remediation_paths") or [],
            "faculty_review": data.get("faculty_review") or {},
            "yaml_path": rel_path,
        }
        module, created = Module.objects.update_or_create(
            module_id=data["module_id"],
            defaults=module_fields,
        )

        self._sync_objectives(module, data.get("learning_objectives") or [])
        self._sync_references(module, data.get("references") or [])
        self._sync_knowledge_checks(module, data.get("knowledge_checks") or [])

        if created:
            return "created"
        return "updated"

    def _sync_objectives(self, module: Module, raw_list: list) -> None:
        seen_ids = set()
        for raw in raw_list:
            obj_id = raw.get("id")
            if not obj_id:
                continue
            seen_ids.add(obj_id)
            LearningObjective.objects.update_or_create(
                module=module,
                objective_id=obj_id,
                defaults={
                    "text": raw.get("text", ""),
                    "domain": raw.get("domain") or "reasoning",
                },
            )
        # Delete objectives no longer present.
        module.learning_objectives.exclude(objective_id__in=seen_ids).delete()

    def _sync_references(self, module: Module, raw_list: list) -> None:
        seen_ids = set()
        for raw in raw_list:
            ref_id = raw.get("id")
            if not ref_id:
                continue
            seen_ids.add(ref_id)
            Reference.objects.update_or_create(
                module=module,
                ref_id=ref_id,
                defaults={
                    "title": raw.get("title", ""),
                    "url": raw.get("url") or "",
                    "version_date": str(raw.get("version_date") or ""),
                    "approved_by": str(raw.get("approved_by") or ""),
                },
            )
        module.references.exclude(ref_id__in=seen_ids).delete()

    def _sync_knowledge_checks(self, module: Module, raw_list: list) -> None:
        seen_ids = set()
        # Pre-load objectives once so we can map id strings to FKs without N queries.
        objectives_by_id = {
            obj.objective_id: obj
            for obj in module.learning_objectives.all()
        }
        for raw in raw_list:
            check_id = raw.get("id")
            if not check_id:
                continue
            seen_ids.add(check_id)
            check, _ = KnowledgeCheck.objects.update_or_create(
                module=module,
                check_id=check_id,
                defaults={
                    "question": raw.get("question", ""),
                    "options": raw.get("options") or [],
                    "correct_option_id": str(raw.get("correct_option_id") or ""),
                    "explanation": raw.get("explanation") or "",
                },
            )
            linked = [
                objectives_by_id[obj_id]
                for obj_id in (raw.get("objective_ids") or [])
                if obj_id in objectives_by_id
            ]
            check.objectives.set(linked)
        module.knowledge_checks.exclude(check_id__in=seen_ids).delete()
