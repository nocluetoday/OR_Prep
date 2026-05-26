# frontend/

Vite + React + TypeScript. Resident-facing UI; faculty admin extensions added later (Django admin covers most admin needs in early chunks).

## Layout

- `src/api/client.ts` — `apiFetch` wrapper: attaches Bearer token, refreshes + retries on 401 (shared singleton promise so concurrent 401s don't trigger multiple refreshes)
- `src/auth/AuthContext.tsx` — provider + `useAuth` hook; bootstraps user from localStorage on mount; exposes `login`, `register`, `logout`
- `src/components/Header.tsx` — top bar: user email + role badge + logout, or login/register links
- `src/components/ProtectedRoute.tsx` — redirects unauthenticated visits to `/login` with `state.from` so login can bounce back
- `src/pages/{Login,Register,Home}.tsx` — auth screens and the protected landing
- `src/App.tsx` — `BrowserRouter` + `AuthProvider` + `Header` + `Routes`
- `public/` — static assets served at root
- `vite.config.ts` — dev server config; proxies `/api/*` to the backend (target from `VITE_PROXY_TARGET`)
- `.env.example` — copy to `.env.local` to override defaults

## Tokens

JWT access + refresh stored in `localStorage` under `rlw_access_token` / `rlw_refresh_token`. `apiFetch` handles refresh transparently; pages and components never touch the tokens directly.

## Commands

Run from `frontend/`:

```
npm install                       # install deps
npm run dev                       # vite dev server on :5173 with HMR
npm run build                     # tsc + vite production build → dist/
npm run preview                   # serve the production build locally
npm run lint                      # eslint
```

If `node`/`npm` resolves to a broken nvm wrapper, call the binary directly:
`/Users/donaldneff/.nvm/versions/node/v24.15.0/bin/npm ...`

## Conventions

- Dev calls hit `/api/...` (relative) — the Vite proxy forwards to Django. No CORS needed in dev.
- Production routing is handled by the reverse proxy (Phase C deploy); the app should keep using relative paths.
- Components: function components + hooks. Co-locate component styles when small; pull into modules when shared.
- Types: prefer `type` over `interface` for data shapes; reserve `interface` for things meant to be extended.
