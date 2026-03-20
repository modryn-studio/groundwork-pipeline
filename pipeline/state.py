from typing import TypedDict


class PipelineState(TypedDict):
    ideas: list[str]
    market_signal: dict | None
    job_id: str
    market_options: list[dict]  # [{name, description, ideas}]
    market: str                 # chosen at Checkpoint 0
