# Deploying Thalace Shops on Render

Two services from `render.yaml`, with Supabase for auth and the database:

| Render service | What | Plan |
|---|---|---|
| `thalace-shops-api` | FastAPI + the shop agents (`backend/`) | Starter, always on, **1 instance** |
| `thalace-shops-app` | The web app (`frontend/`) at **https://shops.thalace.com** | Static site (free) |

The app forwards `/api/*` to the API, so the browser sees one origin, the same as in dev.

During the hackathon both deploy from **`dev`** on every push. Switch `branch:` to `main` in `render.yaml` for the submission.

**Never scale the API past one instance or onto the free tier.** The payment watcher, payout queues and agent runs live inside its process. A second copy would pay twice, and a sleeping one misses payments.

## 1. Render: create the services

1. Render → **New → Blueprint** → repo `calebomondi/thalace-shops`, branch `dev`.
2. Render reads `render.yaml` and asks for every `sync: false` value. Copy each one from `backend/.env`:

| Variable | Service | Value |
|---|---|---|
| `DATABASE_URL` | api | The value of `SUPABASE_DB_CONN_STR`: the **transaction pooler** URL, port **6543** |
| `SUPABASE_BASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SECRET_KEY` | api | From `.env` |
| `ADMIN_BOOTSTRAP_EMAILS` | api | Your admin email(s), comma-separated |
| `NEAR_INTENTS_AGENT_API_KEY` | api | The demo key now; the `naa_…` key once approved (also change `NEAR_INTENTS_AGENT_API_URL`) |
| `NEAR_AI_CLOUD_API_KEY`, `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `OPENROUTER_API_KEY` | api | From `.env` |
| `EXA_API_KEY`, `FIRECRAWL_API_KEY`, `RESEND_API_KEY` | api | From `.env` |
| `KRA_*` | api | From `.env` |
| `VITE_SUPABASE_URL` | app | Same as `SUPABASE_BASE_URL` |
| `VITE_SUPABASE_ANON_KEY` | app | Same as `SUPABASE_ANON_KEY` (the public anon key, never the secret one) |

3. Click **Apply**.
4. **Check the API's hostname.** If Render added a suffix (for example `thalace-shops-api-x1y2.onrender.com`), change the `/api/*` rewrite destination in `render.yaml` to match and push.

## 2. DNS: shops.thalace.com

1. Render → `thalace-shops-app` → Settings → **Custom Domains**: `shops.thalace.com` is already listed by the Blueprint. Render shows the record to add.
2. At the DNS provider for `thalace.com`, add a **CNAME** `shops` → `thalace-shops-app.onrender.com` (use exactly what Render shows).
3. Wait for Render to verify it and issue the certificate.

## 3. Supabase

- **Authentication → URL Configuration**: Site URL `https://shops.thalace.com`; redirect URLs `https://shops.thalace.com/**` and `http://localhost:5173/**`.

## 4. Check it works

- [ ] `https://thalace-shops-api.onrender.com/api/v1/health` → `{"status":"ok",...}`
- [ ] `https://shops.thalace.com/api/v1/health` → the same, through the rewrite
- [ ] `https://shops.thalace.com` shows "Backend: ok (production)"
