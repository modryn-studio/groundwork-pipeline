import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from pipeline.state import PipelineState


class MarketOption(BaseModel):
    name: str = Field(
        description="Short, specific market name (e.g. 'Freelance invoice automation')"
    )
    description: str = Field(
        description="1-2 sentences on the opportunity and who actually pays for it"
    )
    ideas: list[str] = Field(
        description="Ideas from the dump most relevant to this market"
    )


class MarketIdentificationResult(BaseModel):
    markets: list[MarketOption] = Field(
        description="2-3 distinct market opportunities, most promising first"
    )


_llm: ChatAnthropic | None = None


def _get_llm() -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    return _llm


async def stage_0_identify_market(state: PipelineState) -> dict:
    structured_llm = _get_llm().with_structured_output(MarketIdentificationResult)

    ideas_text = "\n".join(f"- {idea}" for idea in state["ideas"])

    system = (
        "You are a market analyst for a solo developer who builds software products. "
        "Analyze the ideas and identify 2-3 distinct, specific market opportunities. "
        "Each market should be a niche with real demand signals and buyers who already spend money. "
        "Be concrete — name the buyer and the pain, not the space."
    )

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f"Builder's ideas:\n{ideas_text}"),
    ]

    result: MarketIdentificationResult = await structured_llm.ainvoke(messages)
    return {"market_options": [m.model_dump() for m in result.markets]}


async def stage_0_skip_to_research(state: PipelineState) -> dict:
    """Market already decided by user — skip identification, set market from signal."""
    signal = state.get("market_signal") or {}
    market = signal.get("label") or signal.get("value", "")
    return {"market": market}


async def checkpoint_0_market_select(state: PipelineState) -> dict:
    user_decision = interrupt({
        "type": "checkpoint",
        "stage": "market_selection",
        "question": "Which market do you want to build for?",
        "options": [
            {
                "label": opt["name"],
                "description": opt["description"],
                "ideas": opt["ideas"],
            }
            for opt in state["market_options"]
        ],
    })
    return {"market": user_decision["chosen_market"]}
