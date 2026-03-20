# Backend Reference — Groundwork Pipeline

Patterns extracted from studying reference implementations before building Stage 0/1.

**Repos studied:**

- `guy-hartstein/company-research-agent` — FastAPI + LangGraph + Tavily + SSE polling (most relevant to our API shape)
- `langchain-ai/open_deep_research` — LangGraph interrupt() + human-in-the-loop state design (most relevant to checkpoints)

---

## API Shape (borrow from company-research-agent)

Three-endpoint pattern that works well with a polling frontend:

```
POST /pipeline/start          → { job_id }             (create job, fire async task)
GET  /pipeline/status/:id     → { state, stage }        (frontend polls this every 2s)
POST /pipeline/resume/:id     → { state }               (send user's checkpoint decision)
GET  /pipeline/result/:id     → { context_md, brand_md } (when state == "complete")
```

The company-research-agent also uses SSE (`StreamingResponse` with `yield f"data: {json.dumps(...)}\n\n"`). Our frontend already polls at 2s intervals — stick with polling, skip SSE unless latency becomes a problem.

**Key pattern:** POST returns immediately with `job_id`. The async work runs in a background task (`asyncio.create_task`). Frontend polls status.

```python
@app.post("/pipeline/start")
async def start(data: PipelineRequest):
    job_id = str(uuid.uuid4())
    asyncio.create_task(run_pipeline(job_id, data))
    return {"job_id": job_id}
```

---

## Job State (use PostgreSQL, not in-memory)

company-research-agent uses an **in-memory dict** (`job_status = {}`). Fine for single-process, dies on restart. We have Neon PostgreSQL — use it.

```python
# Their pattern (in-memory — don't copy this)
job_status: Dict[str, Any] = {}

# Our pattern — store in Neon via psycopg
# table: pipeline_jobs (job_id, state, stage, interrupt_data, result, created_at, updated_at)
```

States: `pending → running → interrupted → running → complete | failed`

`interrupt_data` column holds the JSON payload that goes to the frontend at checkpoint (the research findings + options for the user to choose from).

---

## LangGraph State Schema (borrow from open_deep_research)

open_deep_research's state design is clean. Key insight: use `Annotated[list, operator.add]` for accumulating fields and a custom `override_reducer` when you need to replace rather than append:

```python
def override_reducer(current, new):
    if isinstance(new, dict) and new.get("type") == "override":
        return new.get("value", new)
    return operator.add(current, new)

class PipelineState(TypedDict):
    ideas: list[str]                                          # input
    market: str                                               # set at Checkpoint 0
    raw_research: Annotated[list[str], operator.add]          # accumulated by workers
    curated_findings: Annotated[list[str], override_reducer]  # can be replaced
    differentiation_gap: str                                  # set at Checkpoint 1
    context_md: str                                           # final output
    brand_md: str                                             # final output
    job_id: str                                               # passed to all nodes
```

---

## Parallel Search Pattern (borrow from company-research-agent)

company-research-agent's `base.py` shows the exact pattern: generate N queries, fire them all via `asyncio.gather`, process results.

```python
# Their pattern — runs all Tavily searches simultaneously
search_tasks = [
    self.tavily_client.search(query, search_depth="basic", max_results=5)
    for query in queries
]
results = await asyncio.gather(*search_tasks, return_exceptions=True)

# Process merged results
merged_docs = {}
for query, result in zip(queries, results):
    if isinstance(result, Exception):
        continue  # log and skip, don't crash
    for item in result.get("results", []):
        merged_docs[item["url"]] = item
```

**Key details:**

- `return_exceptions=True` — gather doesn't throw if one search fails
- Dedup by URL (dict keyed by URL, last write wins — fine for our use case)
- Tavily returns a `score` field (0.0–1.0) on each result — use it for curation

---

## Curation / Scoring (borrow from company-research-agent curator.py)

Curator filters Tavily results using Tavily's own relevance score. Threshold 0.4 works well in practice. Cap per category to avoid token blowout in synthesis.

```python
RELEVANCE_THRESHOLD = 0.4
MAX_DOCS_PER_CATEGORY = 30

def curate(docs: list[dict]) -> list[dict]:
    scored = [d for d in docs if float(d.get("score", 0)) >= RELEVANCE_THRESHOLD]
    scored.sort(key=lambda d: float(d["score"]), reverse=True)
    return scored[:MAX_DOCS_PER_CATEGORY]
```

For Groundwork research workers, categories map to:

- `pain_researcher` — Reddit complaints, job-to-be-done threads
- `buyer_researcher` — "what would you pay for" threads, willingness signals
- `competitor_researcher` — product listings, pricing pages
- `pricing_researcher` — SaaS pricing benchmarks

---

## Checkpoint / interrupt() Pattern (borrow from open_deep_research)

This is the key pattern company-research-agent doesn't have (no human-in-loop). open_deep_research uses LangGraph's `interrupt()`:

```python
from langgraph.types import interrupt

def checkpoint_node(state: PipelineState) -> PipelineState:
    # Pause here and surface data to the frontend
    user_decision = interrupt({
        "type": "checkpoint",
        "stage": "market_selection",   # or "differentiation"
        "options": state["market_options"],
        "research": state["raw_research"],
    })
    # Execution resumes here when /pipeline/resume is called
    return {**state, "market": user_decision["chosen_market"]}
```

**How it works end-to-end:**

1. Pipeline runs until `interrupt()` → LangGraph saves state to checkpointer (PostgreSQL)
2. Status endpoint returns `state: "interrupted"` + `interrupt_data`
3. Frontend shows checkpoint UI to user
4. User picks → POST `/pipeline/resume/:id` with decision
5. LangGraph resumes from saved state via `Command(resume=user_decision)`

**Checkpointer setup (PostgreSQL):**

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    graph = pipeline.compile(checkpointer=checkpointer)
    # thread_id ties all calls to the same job
    config = {"configurable": {"thread_id": job_id}}
```

---

## Groundwork Pipeline — Node Map

```
ideas[] + market_signal
    ↓
[Stage 0] market_identifier
  LLM: rank / confirm market from idea dump + signal
    ↓
[Checkpoint 0] interrupt() → frontend shows market options
  user picks market
    ↓
[Stage 1] parallel Tavily workers (asyncio.gather)
  pain_researcher      → "site:reddit.com [market] frustrated with"
  buyer_researcher     → "site:reddit.com [market] I wish there was"
  competitor_researcher → "[market] tool pricing"
  pricing_researcher   → "[market] SaaS how much pay"
    ↓
[Curator] score filter ≥ 0.4, top 30 per category
    ↓
[Synthesis] LLM: identify 3 differentiation gaps from curated findings
    ↓
[Checkpoint 1] interrupt() → frontend shows gap options
  user picks gap
    ↓
[Generator] LLM: write context.md + brand.md from all decisions
    ↓
result stored in Neon, status → "complete"
```

---

## Tavily Query Patterns That Work

Patterns from studying what gpt-researcher and company-research-agent actually query:

```python
# Pain signals
f"site:reddit.com {market} frustrated annoyed hate"
f"site:reddit.com {market} wish there was a tool"
f"site:reddit.com {market} how do you handle"

# Buyer signals
f"site:reddit.com {market} would pay for"
f"site:reddit.com {market} software recommendation"
f"Product Hunt {market} tool reviews"
f"Indie Hackers {market} revenue"

# GitHub interest signals (especially for dev tool markets)
f"site:github.com {market} tool"
f"github {market} open source stars"
# Note: high-star repos with no commercial wrapper = demand without a product.
# Treat the same as a paid competitor — what problem, what's missing, what do people fork.

# Competitor signals
f"{market} software pricing plans"
f"{market} tool alternatives"
f"best {market} SaaS comparison"

# Pricing benchmarks
f"{market} SaaS pricing per month"
f"{market} tool how much does it cost"
```

Use `search_depth="advanced"` for competitor/pricing queries where depth matters. Use `"basic"` for Reddit threads (faster, cheaper).

---

## What to Skip from These Repos

- **MongoDB** (company-research-agent) — we have Neon PostgreSQL, use it
- **PDF generation** (company-research-agent) — not in Groundwork V1
- **SSE streaming** — polling is simpler and already wired in the frontend
- **Multi-model setup** (Gemini + GPT fallback in company-research-agent) — start with one model
- **Docker + docker-compose** — Railway handles deployment, no local Docker needed
