# backend/

Django 5.2 + Django REST Framework. Source of truth for users, modules, progress, and uploads at runtime.

See [CLAUDE.md](CLAUDE.md) for the directory layout, dev commands, and conventions. See [../docs/roadmap.md](../docs/roadmap.md) for what each future chunk will add here.

## Quick start

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Then `curl http://127.0.0.1:8000/api/health/` should return `{"status":"ok","db":"ok","now":"..."}`.
