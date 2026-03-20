import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from pydantic import BaseModel

from db import create_job, create_tables, get_job, update_job

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

compiled_graph = None
_background_tasks: set = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global compiled_graph

    # AsyncPostgresSaver requires autocommit=True + dict_row
    conn = await psycopg.AsyncConnection.connect(
        NEON_DATABASE_URL,
        autocommit=True,
        row_factory=dict_row,
    )
    checkpointer = AsyncPostgresSaver(conn)
    try:
        await checkpointer.setup()
    except psycopg.errors.UniqueViolation:
        pass  # migrations already applied on a previous startup

    from pipeline.graph import build_graph
    compiled_graph = build_graph(checkpointer)

    await create_tables()

    yield

    await conn.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


class PipelineStartRequest(BaseModel):
    ideas: list[str]
    market_signal: dict | None = None


class ResumeRequest(BaseModel):
    decision: dict


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/pipeline/start")
async def pipeline_start(body: PipelineStartRequest):
    if not body.ideas:
        raise HTTPException(status_code=400, detail="ideas required")

    job_id = str(uuid.uuid4())
    await create_job(job_id)

    task = asyncio.create_task(
        run_pipeline_task(job_id, body.ideas, body.market_signal)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"thread_id": job_id}


@app.get("/pipeline/status/{job_id}")
async def pipeline_status(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "state": job["state"],
        "stage": job["stage"],
        "interrupt": json.loads(job["interrupt_data"]) if job["interrupt_data"] else None,
        "result": json.loads(job["result"]) if job["result"] else None,
    }


@app.post("/pipeline/resume/{job_id}")
async def pipeline_resume(job_id: str, body: ResumeRequest):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["state"] != "interrupted":
        raise HTTPException(status_code=400, detail="Job is not waiting for input")

    task = asyncio.create_task(run_resume_task(job_id, body.decision))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "resuming"}


async def run_pipeline_task(
    job_id: str, ideas: list[str], market_signal: dict | None
) -> None:
    config = {"configurable": {"thread_id": job_id}}
    initial_state = {
        "ideas": ideas,
        "market_signal": market_signal,
        "job_id": job_id,
        "market_options": [],
        "market": "",
    }
    await update_job(job_id, state="running", stage="stage_0")
    try:
        await compiled_graph.ainvoke(initial_state, config)
        graph_state = await compiled_graph.aget_state(config)
        if graph_state.next:
            interrupt_val: dict = {}
            if graph_state.tasks and graph_state.tasks[0].interrupts:
                interrupt_val = graph_state.tasks[0].interrupts[0].value
            await update_job(
                job_id,
                state="interrupted",
                stage="checkpoint_0",
                interrupt_data=json.dumps(interrupt_val),
            )
        else:
            await update_job(job_id, state="complete")
    except Exception:
        await update_job(job_id, state="failed")
        raise


async def run_resume_task(job_id: str, decision: dict) -> None:
    config = {"configurable": {"thread_id": job_id}}
    await update_job(job_id, state="running", stage="resume_0")
    try:
        await compiled_graph.ainvoke(Command(resume=decision), config)
        graph_state = await compiled_graph.aget_state(config)
        if graph_state.next:
            # Another checkpoint exists (future stages) — surface it
            interrupt_val: dict = {}
            if graph_state.tasks and graph_state.tasks[0].interrupts:
                interrupt_val = graph_state.tasks[0].interrupts[0].value
            await update_job(
                job_id,
                state="interrupted",
                stage=graph_state.next[0],
                interrupt_data=json.dumps(interrupt_val),
            )
        else:
            chosen_market = decision.get("chosen_market", "")
            await update_job(
                job_id,
                state="complete",
                result=json.dumps({"market_confirmed": True, "market": chosen_market}),
            )
    except Exception:
        await update_job(job_id, state="failed")
        raise
