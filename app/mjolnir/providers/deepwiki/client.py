"""DeepWiki MCP client for repository-wide context.

Communicates with Cognition's DeepWiki MCP server via JSON-RPC over HTTP.
Provides read_wiki_structure, read_wiki_contents, and ask_question tools.
"""
import json
from enum import Enum

import httpx

from utilities.logger import logger

DEFAULT_MCP_URL = "https://mcp.deepwiki.com/mcp"

READ_WIKI_STRUCTURE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_wiki_structure",
        "description": "Get a list of documentation topics for a repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "repoName": {
                    "type": "string",
                    "description": "GitHub repository in owner/repo format.",
                },
            },
            "required": ["repoName"],
        },
    },
}

READ_WIKI_CONTENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_wiki_contents",
        "description": "View full documentation about a GitHub repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "repoName": {
                    "type": "string",
                    "description": "GitHub repository in owner/repo format.",
                },
            },
            "required": ["repoName"],
        },
    },
}

ASK_QUESTION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_question",
        "description": "Ask any question about a repository and get an AI-powered answer.",
        "parameters": {
            "type": "object",
            "properties": {
                "repoName": {
                    "type": "string",
                    "description": "GitHub repository in owner/repo format.",
                },
                "question": {
                    "type": "string",
                    "description": "The question to ask about the repository.",
                },
            },
            "required": ["repoName", "question"],
        },
    },
}


class DeepWikiContextStatus(str, Enum):
    verified = "verified"
    revision_unverified = "revision-unverified"
    unindexed = "unindexed"
    unauthorized = "unauthorized"
    unavailable = "unavailable"
    not_applicable = "not-applicable"


def _parse_sse_response(text: str) -> dict:
    """Parse SSE response, merging all result events and filtering notifications.

    DeepWiki sends progress notifications (method: notifications/message)
    before the actual result. We skip those and only collect events with
    a 'result' key, merging their content arrays.
    """
    result_events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            try:
                event = json.loads(data_str)
                if "result" in event:
                    result_events.append(event)
            except json.JSONDecodeError:
                continue
    if not result_events:
        return {}

    merged = result_events[0]
    if len(result_events) > 1:
        for event in result_events[1:]:
            extra = event.get("result", {}).get("content", [])
            merged["result"]["content"].extend(extra)
    return merged


class DeepWikiClient:
    def __init__(self, repo_name: str, mcp_url: str = DEFAULT_MCP_URL):
        self.repo_name = repo_name
        self.mcp_url = mcp_url
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _call(self, method: str, params: dict) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        try:
            response = httpx.post(
                self.mcp_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                timeout=120.0,
            )
            if response.status_code != 200:
                logger.warning(f"DeepWiki HTTP {response.status_code}: {response.text[:200]}")
                return f"DeepWiki unavailable (HTTP {response.status_code})"

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type or "event-stream" in content_type:
                data = _parse_sse_response(response.text)
            else:
                try:
                    data = response.json()
                except Exception:
                    logger.warning(f"DeepWiki non-JSON response: {response.text[:200]}")
                    return f"DeepWiki unavailable (invalid response)"

            if "error" in data:
                logger.warning(f"DeepWiki RPC error: {data['error']}")
                return f"DeepWiki error: {data['error'].get('message', 'unknown')}"
            result = data.get("result", data)
            if isinstance(result, dict) and "content" in result:
                parts = []
                for item in result["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item["text"])
                return "\n".join(parts)
            return json.dumps(result)
        except httpx.TimeoutException:
            logger.warning("DeepWiki request timed out")
            return "DeepWiki unavailable (timeout)"
        except Exception as e:
            logger.warning(f"DeepWiki request failed: {e}")
            return "DeepWiki unavailable (connection failed)"

    def read_wiki_structure(self) -> str:
        return self._call("tools/call", {
            "name": "read_wiki_structure",
            "arguments": {"repoName": self.repo_name},
        })

    def read_wiki_contents(self) -> str:
        return self._call("tools/call", {
            "name": "read_wiki_contents",
            "arguments": {"repoName": self.repo_name},
        })

    def ask_question(self, question: str) -> str:
        return self._call("tools/call", {
            "name": "ask_question",
            "arguments": {
                "repoName": self.repo_name,
                "question": question,
            },
        })

    @staticmethod
    def get_tool_definition(name: str) -> dict | None:
        tools = {
            "read_wiki_structure": READ_WIKI_STRUCTURE_SCHEMA,
            "read_wiki_contents": READ_WIKI_CONTENTS_SCHEMA,
            "ask_question": ASK_QUESTION_SCHEMA,
        }
        return tools.get(name)

    @staticmethod
    def get_all_tool_definitions() -> list:
        return [
            READ_WIKI_STRUCTURE_SCHEMA,
            READ_WIKI_CONTENTS_SCHEMA,
            ASK_QUESTION_SCHEMA,
        ]
