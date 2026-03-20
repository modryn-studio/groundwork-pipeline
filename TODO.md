# Pre-Launch TODO — End-to-End Test

Steps required before the full flow works: `/start` → dump ideas → pick market → "Run pipeline →" → `/run/[threadId]` → Checkpoint 0 → lock in → "Market locked."

---

## 1. Neon PostgreSQL

Get a connection string. Free tier works.

- [ ] Create a Neon project at neon.tech
- [ ] Copy the connection string — format: `postgresql://user:pass@host/db?sslmode=require`
- [ ] Note: `pipeline_jobs` table and LangGraph checkpoint tables are created automatically on first startup (`db.create_tables()` + `checkpointer.setup()` both run in lifespan)

---

## 2. Local dev test

Run locally before deploying to Railway.

```powershell
cd C:\Users\Luke\Documents\2026\Mar-19\groundwork-pipeline

# Create virtualenv
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt

# Configure env
copy .env.example .env
# Fill in: ANTHROPIC_API_KEY, NEON_DATABASE_URL, ALLOWED_ORIGINS=http://localhost:3000

# Run
uvicorn main:app --reload
```

- [ ] `GET http://localhost:8000/health` → `{ "status": "ok" }`
- [ ] `POST http://localhost:8000/pipeline/start` with `{ "ideas": ["some idea"], "market_signal": null }` → `{ "thread_id": "..." }`
- [ ] `GET http://localhost:8000/pipeline/status/{thread_id}` → watch state go `pending → running → interrupted`
- [ ] Interrupt data includes `{ type: "checkpoint", stage: "market_selection", options: [...] }`
- [ ] `POST http://localhost:8000/pipeline/resume/{thread_id}` with `{ "decision": { "chosen_market": "..." } }` → state goes to `complete`

---

## 3. Wire frontend to local backend

In `C:\Users\Luke\Documents\2026\Mar-19\groundwork\.env.local`:

```
PIPELINE_API_URL=http://localhost:8000
```

- [ ] Restart Next.js dev server
- [ ] Full browser flow: `/start` → ideas → market → "Run pipeline →" → `/run/[threadId]` → pick market → "Market locked."

---

## 4. Railway deploy

- [ ] Create new Railway service from the `groundwork-pipeline` GitHub repo
- [ ] Set env vars in Railway dashboard:
  - `ANTHROPIC_API_KEY`
  - `NEON_DATABASE_URL`
  - `ALLOWED_ORIGINS=https://modrynstudio.com,http://localhost:3000`
- [ ] Confirm Railway start command picks up `Procfile`: `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
- [ ] Note Railway's public URL (e.g. `https://groundwork-pipeline-production.up.railway.app`)

---

## 5. Connect frontend to Railway

Update `PIPELINE_API_URL` in Vercel environment variables (or `.env.local` for local testing against prod backend):

```
PIPELINE_API_URL=https://groundwork-pipeline-production.up.railway.app
```

- [ ] Redeploy frontend (or `vercel env pull` + restart dev server)
- [ ] Full end-to-end test against Railway backend

---

## Known gaps for post-test

These are explicitly out of scope until the end-to-end test passes:

- Stage 1 Tavily research workers
- Stage 2 synthesis + Checkpoints 1-3
- Result download (context.md + brand.md)
- LangSmith tracing
- Error boundaries on `/run/[threadId]` (currently just a plain text message)
