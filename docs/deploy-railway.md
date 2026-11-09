# Deploying Thalace Shops on Railway

Two services from this repo, with Supabase for auth and the database. Their build and deploy settings are infrastructure as code in **`.railway/railway.ts`** (Railway's `railway.json` config-as-code is deprecated):

| Railway service | Root directory | What |
|---|---|---|
| `api` | `/backend` | FastAPI + the shop agents + the payment watcher (`backend/Dockerfile`) |
| `app` | `/frontend` | The web app at **https://shops.thalace.com**, served by Caddy, which forwards `/api/*` and `/mcp` to `api` over Railway's private network (`frontend/Dockerfile`, `frontend/Caddyfile`) |

The browser only ever talks to `app`, so there's one origin and no CORS. `api` needs no public domain.

**Run `api` as exactly one replica, always on.** The payment watcher and payout queue run inside its process: two copies would race each other, and a sleeping one would miss payments. Railway's default is one replica, and `.railway/railway.ts` restarts it on failure; don't turn on serverless (app sleeping) for `api`.

Migrations run before each `api` deploy (the pre-deploy command `alembic upgrade head` in `.railway/railway.ts`); a failed migration stops the deploy.

## 1. Create the project

1. Railway → **New project → Deploy from GitHub repo** → `calebomondi/thalace-shops`.
2. Make two services from the same repo. For each, in **Settings**:
   - **Source → Root directory**: `/backend` for `api`, `/frontend` for `app`.
   - **Source → Branch**: `main`. Work happens on `dev` and reaches `main` through a PR, so every deploy is reviewed.
3. Rename them `api` and `app` (the variables below and `.railway/railway.ts` refer to them by name).
4. Apply the build and deploy settings from the repo root (needs the [Railway CLI](https://docs.railway.com/cli) and Node):

   ```sh
   railway link --project <project> --environment production
   (cd .railway && npm install)
   railway config plan      # review: builders, pre-deploy, health checks, restart policy
   railway config apply
   ```

   Variables in `.railway/railway.ts` are listed by name with `preserve()`: their values stay in Railway. A variable added in Railway later must be added there too (as `preserve()`), or the next plan refuses to run.

## 2. Variables

### `api`

| Variable | Value |
|---|---|
| `PORT` | `8000` (fixed, so `app` knows where to reach it) |
| `ENVIRONMENT` | `production` |
| `LOG_FORMAT` | `json` |
| `CLIENT_IP_HEADER` | `x-real-ip` (Caddy rewrites `x-forwarded-for` with Railway's edge address) |
| `FRONTEND_BASE_URL` | `https://shops.thalace.com` (passkeys are bound to it for good) |
| `DATABASE_URL` | Supabase's **transaction pooler** URL, port **6543** (the value of `SUPABASE_DB_CONN_STR`). A deploy briefly runs old and new side by side; the session pooler's client cap can't hold both. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `4`, `4` |
| `SUPABASE_BASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SECRET_KEY` | From `backend/.env` |
| `ADMIN_BOOTSTRAP_EMAILS` | Your admin email(s), comma-separated |
| `NEAR_INTENTS_AGENT_API_KEY`, `NEAR_INTENTS_AGENT_API_URL` | The demo key and `https://api.demo.agentsonintents.com` now; the `naa_…` key and the production URL once approved |
| `NEAR_MAINNET_PLATFORM_TREASURY_WALLET_ADDRESS` | `thalaceshops.near` |
| `SHOP_GRANT_KEY` | A **new** Fernet key for production (`uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Never change it once shops are live. |
| `NEAR_AI_CLOUD_API_KEY`, `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `OPENROUTER_API_KEY` | From `backend/.env` |
| `FIRECRAWL_API_KEY`, `EXA_API_KEY`, `RESEND_API_KEY` | From `backend/.env` |
| `KRA_*` | From `backend/.env` |

### `app`

| Variable | Value |
|---|---|
| `API_UPSTREAM` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:${{api.PORT}}` (Railway fills in the private address) |
| `VITE_SUPABASE_URL` | Same as `SUPABASE_BASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | Same as `SUPABASE_ANON_KEY` (the public anon key, never the secret one) |

The `VITE_*` values are baked in at build time (Railway passes them to the Docker build): redeploy `app` after changing them.

## 3. Domain

1. `app` → **Settings → Networking → Custom domain** → `shops.thalace.com`. Railway shows the DNS record.
2. At the DNS provider for `thalace.com`, add the **CNAME** `shops` → the target Railway shows.
3. Wait for Railway to verify it and issue the certificate.

## 4. Supabase

**Authentication → URL Configuration**: Site URL `https://shops.thalace.com`; redirect URLs `https://shops.thalace.com/**`, `http://localhost:5180/**` and `https://*.trycloudflare.com/**`.

## 5. Check it works

- [ ] `https://shops.thalace.com/api/v1/health` → `{"status":"ok","environment":"production",...}`
- [ ] `https://shops.thalace.com` loads and signing in works
- [ ] A deep link such as `https://shops.thalace.com/s/<slug>` loads the app, not a 404

## Run the images locally

```sh
docker network create ts-net
docker build -t thalace-shops-api backend
docker build -t thalace-shops-app --build-arg VITE_SUPABASE_URL=... --build-arg VITE_SUPABASE_ANON_KEY=... frontend
docker run -d --name ts-api --network ts-net -e PORT=8000 -e WATCHER_ENABLED=false thalace-shops-api
docker run -d --name ts-app --network ts-net -e PORT=8080 -e API_UPSTREAM=http://ts-api:8000 -p 8188:8080 thalace-shops-app
curl localhost:8188/api/v1/health
```
