from __future__ import annotations

from typing import Any, Callable


def build_langgraph(
    work_fn: Callable[[dict[str, Any]], dict[str, Any]], verify_fn: Callable[[dict[str, Any]], dict[str, Any]]
):
    """Build an optional LangGraph adapter without coupling protocol-core to LangGraph."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install the optional dependency with: pip install -e '.[langgraph]'") from exc

    graph = StateGraph(dict)
    graph.add_node("worker", work_fn)
    graph.add_node("verifier", verify_fn)
    graph.add_edge(START, "worker")
    graph.add_edge("worker", "verifier")
    graph.add_edge("verifier", END)
    return graph.compile()
