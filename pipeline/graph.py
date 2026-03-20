from langgraph.graph import END, START, StateGraph

from pipeline.nodes import (
    checkpoint_0_market_select,
    stage_0_identify_market,
    stage_0_skip_to_research,
)
from pipeline.state import PipelineState


def _route_entry(state: PipelineState) -> str:
    """Branch at entry: market already known → skip Stage 0 and Checkpoint 0."""
    if state.get("market_signal"):
        return "skip_to_research"
    return "stage_0"


def build_graph(checkpointer):
    builder = StateGraph(PipelineState)

    builder.add_node("stage_0", stage_0_identify_market)
    builder.add_node("checkpoint_0", checkpoint_0_market_select)
    builder.add_node("skip_to_research", stage_0_skip_to_research)

    builder.add_conditional_edges(START, _route_entry)
    builder.add_edge("stage_0", "checkpoint_0")
    builder.add_edge("checkpoint_0", END)
    builder.add_edge("skip_to_research", END)

    return builder.compile(checkpointer=checkpointer)
