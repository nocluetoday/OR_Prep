# docker/

Dev stack: Postgres + Django backend + Vite/React frontend on a single compose network. Hot reload via bind mounts. Postgres is internal-only (no host port).

## Layout

- `docker-compose.yml` — three services + named volumes
- `backend.Dockerfile` — Python 3.13 slim, dev image (code mounted at runtime)
- `frontend.Dockerfile` — Node 24 alpine, dev image (code mounted at runtime)
- `.env.example` — copy to `.env` for `docker compose up`

Production multi-stage images and orchestration land in Phase C.

## Commands

Run from this directory:

```
cp .env.example .env              # first time only
docker compose up --build         # build + start, foreground
docker compose up -d --build      # detached
docker compose ps                 # status
docker compose logs -f backend    # tail one service
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py makemigrations
docker compose down               # stop, keep data
docker compose down -v            # stop, wipe pgdata + cached deps
```

When deps change:

```
docker compose build backend      # rebuild after requirements.txt change
docker compose build frontend     # rebuild after package.json change
docker compose up -d              # restart with the new image
```

## How hot reload works

- Backend: `../backend` mounted at `/app`; `manage.py runserver` auto-reloads on file changes.
- Frontend: `../frontend` mounted at `/app`; Vite's file watcher triggers HMR.
- The host's `.venv/` and `node_modules/` are masked by named volumes (`backend-venv`, `frontend-node-modules`) so macOS-built binaries don't leak into the Linux containers.

## Ports

| Service  | Host port | Container port | Exposed? |
|----------|-----------|----------------|----------|
| frontend | 5173      | 5173           | yes      |
| backend  | 8000      | 8000           | yes      |
| postgres | —         | 5432           | no       |

Postgres is internal-only. To inspect: `docker compose exec postgres psql -U rlw rlw_dev`.

## Switching between native and Docker dev

The backend reads `DATABASE_URL` from env via django-environ. With the variable unset (native `runserver` from `backend/`), it falls back to local sqlite. Compose sets `DATABASE_URL` to the Postgres service, so the same code talks to Postgres without changes.

Frontend uses the same dual approach: `VITE_PROXY_TARGET` defaults to `http://127.0.0.1:8000` for native dev; compose overrides it to `http://backend:8000` so the container can reach the backend service by name.

Don't run native and Docker dev on the same ports at the same time — `docker compose stop frontend` or `docker compose stop backend` first.
