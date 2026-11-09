
"""
Graph assembly for the AI Research Intelligence Pipeline.

This module builds and compiles the LangGraph StateGraph.

Execution path:
    START -> research -> analysis -> report -> END

The graph owns orchestration, including node registration, edges,
and per-node retry policies for transient LLM/API failures.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RetryPolicy

from config import load_settings
from nodes import (
    LLMClient,
    make_analysis_node,
    make_report_node,
    make_research_node,
)
from state import ResearchState


def get_llm() -> LLMClient:
    """Build the real Gemini client used outside of tests.

    Imported lazily so that modules which only need the graph structure
    can work with FakeLLM without requiring a configured API key.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = load_settings()

    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Copy .env.example to .env "
            "and add your key, or configure it via Colab Secrets."
        )

    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
    )


def build_graph(
    llm: LLMClient | None = None,
) -> CompiledStateGraph:
    """Construct and compile the research pipeline StateGraph.

    Args:
        llm: An object implementing invoke(prompt) -> response.
             If omitted, a real Gemini client is created.
             Tests can pass FakeLLM to avoid API calls.
    """
    resolved_llm = llm if llm is not None else get_llm()

    settings = load_settings()

    retry_policy = RetryPolicy(
        max_attempts=settings.max_retries,
        initial_interval=settings.retry_initial_interval,
        backoff_factor=settings.retry_backoff_factor,
        retry_on=Exception,
    )

    graph = StateGraph(ResearchState)

    graph.add_node(
        "research",
        make_research_node(resolved_llm),
        retry_policy=retry_policy,
    )

    graph.add_node(
        "analysis",
        make_analysis_node(resolved_llm),
        retry_policy=retry_policy,
    )

    graph.add_node(
        "report",
        make_report_node(resolved_llm),
        retry_policy=retry_policy,
    )

    graph.add_edge(START, "research")
    graph.add_edge("research", "analysis")
    graph.add_edge("analysis", "report")
    graph.add_edge("report", END)

    return graph.compile()
