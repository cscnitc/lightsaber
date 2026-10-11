"""Per-call token usage recorder for the OpenAI-compatible provider.

Competition evidence requires input/output/total token counts per bug, so every
LLM call appends one record. Call dump_usage(run_dir) at the end of a run to
persist usage.jsonl plus totals to usage.json.
"""
import json
import threading
from pathlib import Path

from utilities.logger import logger

_lock = threading.Lock()
_calls: list = []


def record(model: str, phase: str, input_tokens: int, output_tokens: int):
    with _lock:
        _calls.append(
            {
                "model": model,
                "phase": phase or "",
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
            }
        )


def totals():
    with _lock:
        calls = list(_calls)
    inp = sum(c["input_tokens"] for c in calls)
    out = sum(c["output_tokens"] for c in calls)
    return {"calls": len(calls), "input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


def dump_usage(run_dir: str):
    with _lock:
        calls = list(_calls)
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    with open(run_path / "usage.jsonl", "w", encoding="utf-8") as f:
        for c in calls:
            f.write(json.dumps(c) + "\n")
    t = totals()
    with open(run_path / "usage.json", "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2)
    logger.info(
        f"Token usage: {t['calls']} calls, "
        f"input={t['input_tokens']}, output={t['output_tokens']}, total={t['total_tokens']}."
    )
    return t
