import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["NEON_DATABASE_URL"]

# Column whitelist prevents f-string injection even though fields come from internal code
_ALLOWED_COLUMNS = {"state", "stage", "interrupt_data", "result"}


async def create_tables() -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                job_id TEXT PRIMARY KEY,
                state TEXT NOT NULL DEFAULT 'pending',
                stage TEXT,
                interrupt_data TEXT,
                result TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.commit()


async def create_job(job_id: str) -> None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        await conn.execute(
            "INSERT INTO pipeline_jobs (job_id, state) VALUES (%s, %s)",
            (job_id, "pending"),
        )
        await conn.commit()


async def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    invalid = set(fields.keys()) - _ALLOWED_COLUMNS
    if invalid:
        raise ValueError(f"Invalid column(s): {invalid}")
    set_clauses = ", ".join(f"{k} = %s" for k in fields) + ", updated_at = NOW()"
    values = list(fields.values()) + [job_id]
    async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
        await conn.execute(
            f"UPDATE pipeline_jobs SET {set_clauses} WHERE job_id = %s",
            values,
        )
        await conn.commit()


async def get_job(job_id: str) -> dict | None:
    async with await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row) as conn:
        cur = await conn.execute(
            "SELECT job_id, state, stage, interrupt_data, result "
            "FROM pipeline_jobs WHERE job_id = %s",
            (job_id,),
        )
        return await cur.fetchone()
