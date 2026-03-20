from langgraph.graph import END, START, StateGraph

from pipeline.nodes import checkpoint_0_market_select, stage_0_identify_market
from pipeline.state import PipelineState


def build_graph(checkpointer):
    builder = StateGraph(PipelineState)

    builder.add_node("stage_0", stage_0_identify_market)
    builder.add_node("checkpoint_0", checkpoint_0_market_select)

    builder.add_edge(START, "stage_0")
    builder.add_edge("stage_0", "checkpoint_0")
    builder.add_edge("checkpoint_0", END)

    return builder.compile(checkpointer=checkpointer)
