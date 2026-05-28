# apps.modules is the legacy curriculum schema (Module / LearningObjective /
# KnowledgeCheck / Reference). The briefing path does not read these; they
# remain in the DB only for backwards compatibility with the old
# `import_modules` YAML importer. Intentionally NOT registered in admin —
# faculty authoring lives in apps.cases (CaseTemplate + SurgeonPreference).
#
# If you need to inspect or edit a legacy Module row, use the Django shell:
#     .venv/bin/python manage.py shell -c "from apps.modules.models import Module; ..."
