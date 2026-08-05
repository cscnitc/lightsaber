"""Multi-turn doubt-resolution loop for LLM agents.

Generic protocol: the agent can output DOUBT: <question> and the orchestrator
routes the question to a context provider (DeepWiki, internal tools, etc.)
and feeds the response back. Continues until the agent produces a final answer
or max_turns is reached.
"""
import re

from utilities.logger import logger

DOUBT_MARKER = "DOUBT:"
MAX_TURNS = 10


def run_with_doubts(
    generate_fn,
    initial_messages: list,
    context_resolver,
    max_turns: int = MAX_TURNS,
    response_schema=None,
) -> str:
    """Run a multi-turn agent loop with doubt resolution.

    The agent produces text responses. If a response starts with DOUBT: (possibly
    after whitespace), the remainder is treated as a question. The orchestrator
    calls context_resolver(question) to get an answer, feeds it back to the agent,
    and the loop continues.

    When the agent produces a response without DOUBT:, that is treated as the
    final output and returned. If max_turns is reached, the orchestrator appends
    a MAX_TURNS instruction and forces one final generation.

    Args:
        generate_fn: Callable(messages, response_schema=None) -> raw_text.
        initial_messages: List of message dicts (system + user).
        context_resolver: Callable(question: str) -> answer: str.
        max_turns: Maximum doubt-resolution turns before forcing a final answer.
        response_schema: Optional pydantic model for structured output on final call.
    """
    messages = list(initial_messages)
    doubts_resolved = 0

    for turn in range(max_turns):
        logger.debug(f"[Doubt Loop] Turn {turn + 1}/{max_turns}")
        raw = generate_fn(messages)
        if raw is None:
            raw = ""

        # Check for DOUBT: marker — may have leading whitespace/newlines
        stripped = raw.strip()
        if stripped.startswith(DOUBT_MARKER):
            question = stripped[len(DOUBT_MARKER):].strip()
            logger.debug(f"[Doubt Loop] Agent raised DOUBT: {question[:100]}...")

            answer = context_resolver(question)
            logger.debug(f"[Doubt Loop] Resolver returned {len(answer)} chars")

            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"Context response to your doubt:\n\n{answer}\n\n"
                           f"Now continue your analysis. If you have more doubts, "
                           f"use DOUBT: <question>. Otherwise, produce your final output.",
            })
            doubts_resolved += 1
        else:
            # No DOUBT: — this is the final answer
            logger.debug(f"[Doubt Loop] Agent produced final output after {doubts_resolved} doubt(s)")
            return raw

    # Max turns reached — force final answer
    logger.warning(f"[Doubt Loop] MAX_TURNS ({max_turns}) reached after {doubts_resolved} doubt(s). Forcing final output.")
    messages.append({
        "role": "user",
        "content": (
            "You have reached the maximum number of clarification turns. "
            "You MUST produce your final output now. Do NOT use DOUBT: again. "
            "If you are still uncertain, note that in your output and proceed with "
            "your best assessment."
        ),
    })
    return generate_fn(messages, response_schema=response_schema)
