"""Adversarial reviewer using OpenAI chat completions with tool calling."""
import json
import os
import subprocess
from pathlib import Path

from data.review_finding import ReviewFinding
from providers.openai.agents.base import OpenAIMjolnirAgent


def _build_tool_handlers(code_dir: str):
    _code_dir = Path(code_dir).resolve()

    def _safe_path(relative_path: str) -> Path:
        p = (_code_dir / relative_path).resolve()
        if not str(p).startswith(str(_code_dir)):
            raise ValueError(f"Path traversal detected: {relative_path}")
        return p

    def read_file(file_path: str, start_line: int = 1, end_line: int = 0) -> str:
        try:
            target = _safe_path(file_path)
        except ValueError as e:
            return f"Error: {e}"
        if not target.exists() or not target.is_file():
            return f"Error: File '{file_path}' does not exist."
        lines = target.read_text(errors="ignore").splitlines()
        total = len(lines)
        sl = max(1, start_line) - 1
        el = end_line if end_line and end_line > 0 else total
        el = min(el, total)
        output = "\n".join(f"{i + sl + 1}: {line}" for i, line in enumerate(lines[sl:el]))
        if len(output) > 40000:
            output = output[:40000] + "\n... [truncated]"
        return output

    def grep_search(pattern: str, dir_path: str = ".", include_pattern: str = "", case_sensitive: bool = True) -> str:
        try:
            search_dir = _safe_path(dir_path) if dir_path != "." else _code_dir
        except ValueError as e:
            return f"Error: {e}"
        if not search_dir.exists():
            return f"Error: Path '{dir_path}' does not exist."
        try:
            cmd = ["rg", "--no-heading", "--line-number"]
            if not case_sensitive:
                cmd.append("--ignore-case")
            if include_pattern:
                cmd.extend(["--glob", include_pattern])
            cmd.extend([pattern, str(search_dir)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env={**os.environ, "LC_ALL": "C"})
            output = result.stdout or result.stderr or "No matches found."
            if len(output) > 40000:
                output = output[:40000] + "\n... [truncated]"
            return output
        except subprocess.TimeoutExpired:
            return "Error: grep_search timed out."
        except FileNotFoundError:
            return "Error: ripgrep (rg) not found in PATH."

    def glob_search(pattern: str, dir_path: str = ".") -> str:
        try:
            base = _safe_path(dir_path) if dir_path != "." else _code_dir
        except ValueError as e:
            return f"Error: {e}"
        if not base.exists():
            return f"Error: Path '{dir_path}' does not exist."
        matches = sorted(base.rglob(pattern))
        rel_matches = [str(m.relative_to(_code_dir)) for m in matches]
        output = "\n".join(rel_matches[:200])
        if len(rel_matches) > 200:
            output += f"\n... and {len(rel_matches) - 200} more matches."
        return output or "No files matched."

    return {"read_file": read_file, "grep_search": grep_search, "glob_search": glob_search}


_READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Reads the contents of a file from the codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to the file."},
                "start_line": {"type": "integer", "description": "First line (1-indexed)."},
                "end_line": {"type": "integer", "description": "Last line (inclusive)."},
            },
            "required": ["file_path"],
        },
    },
}

_GREP_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "grep_search",
        "description": "Searches for a regex pattern in file contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
                "dir_path": {"type": "string", "description": "Directory to search in."},
                "include_pattern": {"type": "string", "description": "Glob to filter files."},
                "case_sensitive": {"type": "boolean", "description": "Case sensitive search."},
            },
            "required": ["pattern"],
        },
    },
}

_GLOB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "glob_search",
        "description": "Finds files matching a glob pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern."},
                "dir_path": {"type": "string", "description": "Directory to search in."},
            },
            "required": ["pattern"],
        },
    },
}


class OpenAIAdversarialReviewerAgent(OpenAIMjolnirAgent):
    def __init__(self, client, model: str, system_instruction: str, code_dir: str = ""):
        super().__init__(client, model, system_instruction)
        self.code_dir = code_dir
        self.tools = [_READ_FILE_SCHEMA, _GREP_SEARCH_SCHEMA, _GLOB_SEARCH_SCHEMA]
        self.tool_handlers = _build_tool_handlers(code_dir)

    def run(self, finding_json_str: str) -> ReviewFinding:
        messages = self._build_messages(finding_json_str)
        raw_output = self._run_tool_loop(messages, tools=self.tools, tool_handlers=self.tool_handlers)
        if not raw_output:
            response = self._generate(messages, response_schema=ReviewFinding)
            raw_output = self.get_response_text(response)
        if not raw_output:
            raise RuntimeError("Adversarial review failed to produce output.")

        import re
        import json as _json

        obj = None
        for candidate in re.findall(r"\{[^{}]*\}", raw_output, re.DOTALL):
            try:
                obj = _json.loads(candidate)
                if all(k in obj for k in ("title", "severity", "location", "verdict")):
                    break
            except _json.JSONDecodeError:
                continue
        if obj is None:
            try:
                obj = _json.loads(raw_output)
            except _json.JSONDecodeError:
                pass
        if obj is None:
            response = self._generate(messages, response_schema=ReviewFinding)
            obj = _json.loads(self.get_response_text(response))
        return ReviewFinding.model_validate(obj)
