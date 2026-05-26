# docker/

Dev containerization for the Resident Learning Wiki. Three services on a single compose network: Postgres, Django backend, Vite/React frontend. See [CLAUDE.md](CLAUDE.md) for full command reference.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Then open `http://127.0.0.1:5173/`. Postgres runs internal-only; backend on `:8000`; frontend on `:5173`.

First boot also wants migrations:

```bash
docker compose exec backend python manage.py migrate
```

Production multi-stage images and orchestration land in Phase C.
