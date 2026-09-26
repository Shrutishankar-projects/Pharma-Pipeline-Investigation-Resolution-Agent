"""End-to-end trace construction (CLAUDE.md section 19).

Every workflow step -- plan, agent, skill, tool/MCP call, guardrail check,
approval event -- is recorded as a `TraceEvent` (state/models.py) carrying
the shared `trace_id`. Building the event here also emits the matching
structured log line so the two observability surfaces never drift apart.
"""
from __future__ import annotations

import itertools
import time
from contextlib import contextmanager

from observability.logger import log_event
from state.models import TraceEvent, now_iso

_step_counter = itertools.count(1)


def next_step_id(trace_id: str) -> str:
    return f"{trace_id}-step-{next(_step_counter)}"


def record(
    trace_id: str,
    node: str,
    event: str,
    *,
    agent: str | None = None,
    skill: str | None = None,
    tool: str | None = None,
    status: str = "OK",
    detail: str | None = None,
    duration_ms: float | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a trace entry and emit the matching log line.

    Returns a plain dict (not the TraceEvent model instance) so LangGraph's
    checkpointer -- which msgpack-serializes workflow state, including the
    accumulated `trace` list -- never has to serialize a custom pydantic
    type. `TraceEvent` is still used to validate the shape before returning.

    `metadata` carries structured extras that don't warrant their own
    dedicated TraceEvent field (LLM provider/model/tokens, tool input/output
    summaries, etc.) -- one generic extension point instead of a growing
    list of single-purpose columns.
    """
    step_id = next_step_id(trace_id)
    log_event(
        event,
        trace_id=trace_id,
        step_id=step_id,
        node=node,
        agent=agent,
        skill=skill,
        tool=tool,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        metadata=metadata,
    )
    validated = TraceEvent(
        trace_id=trace_id,
        step_id=step_id,
        timestamp=now_iso(),
        node=node,
        agent=agent,
        skill=skill,
        tool=tool,
        event=event,
        status=status,  # type: ignore[arg-type]
        detail=detail,
        duration_ms=duration_ms,
        metadata=metadata,
    )
    return validated.model_dump()


@contextmanager
def timed():
    """Yield a callable returning elapsed milliseconds so far."""
    start = time.perf_counter()
    yield lambda: round((time.perf_counter() - start) * 1000, 2)
