# Pre-Launch TODO — End-to-End Test

Two entry paths through the pipeline:

- **Dump path**: `/start` → dump ideas → "Run pipeline →" → `/run/[threadId]` → Stage 0 clusters ideas → Checkpoint 0 (pick market) → "Market locked."
- **Market path**: `/start` → pick a market → "Run pipeline →" → `/run/[threadId]` → skip Stage 0 + Checkpoint 0 → straight to research

---

## 1. Neon PostgreSQL

Get a connection string. Free tier works.

- [x] Create a Neon project at neon.tech
- [x] Copy the connection string — format: `postgresql://user:pass@host/db?sslmode=require`
- [x] Note: `pipeline_jobs` table and LangGraph checkpoint tables are created automatically on first startup (`db.create_tables()` + `checkpointer.setup()` both run in lifespan)

---

## 2. Local dev test

Run locally before deploying to Render.

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

# Run (Windows — uses SelectorEventLoop required by psycopg async)
python run.py
```

- [x] `GET http://localhost:8001/health` → `{ "status": "ok" }`
- [x] `POST http://localhost:8001/pipeline/start` with `{ "ideas": ["some idea"], "market_signal": null }` → `{ "thread_id": "..." }`
- [x] `GET http://localhost:8001/pipeline/status/{thread_id}` → watch state go `pending → running → interrupted`
- [x] Interrupt data includes `{ type: "checkpoint", stage: "market_selection", options: [...] }`
- [x] `POST http://localhost:8001/pipeline/resume/{thread_id}` with `{ "decision": { "chosen_market": "..." } }` → state goes to `complete`

---

## 3. Wire frontend to local backend

In `C:\Users\Luke\Documents\2026\Mar-19\groundwork\.env.local`:

```
PIPELINE_API_URL=http://localhost:8001
```

- [x] Restart Next.js dev server
- [x] Full browser flow: `/start` → ideas → market → "Run pipeline →" → `/run/[threadId]` → pick market → "Market locked."

---

## 4. Render deploy

- [x] Create new Web Service from the `groundwork-pipeline` GitHub repo
- [x] Build: `pip install -r requirements.txt`
- [x] Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- [x] Set env vars: `ANTHROPIC_API_KEY`, `NEON_DATABASE_URL`, `ALLOWED_ORIGINS`
- [x] URL: https://groundwork-pipeline.onrender.com

---

## 5. Connect frontend to Render

Add `PIPELINE_API_URL` in Vercel environment variables:

```
PIPELINE_API_URL=https://groundwork-pipeline.onrender.com
```

- [x] Add `PIPELINE_API_URL=https://groundwork-pipeline.onrender.com` in Vercel dashboard → redeploy
- [ ] Full end-to-end test: `modrynstudio.com/tools/groundwork/start` → ideas → market → "Run pipeline →" → pick market → "Market locked." (blocked on modryn-studio-v2 rewrite for `/tools/groundwork`)

---

## Known gaps for post-test

These are explicitly out of scope until the end-to-end test passes:

- Stage 1 Tavily research workers
- Stage 2 synthesis + Checkpoints 1-3
- Result download (context.md + brand.md)
- LangSmith tracing
- Error boundaries on `/run/[threadId]` (currently just a plain text message)
