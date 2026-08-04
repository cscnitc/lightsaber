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
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.warning(f"DeepWiki HTTP {response.status_code}: {response.text[:200]}")
                return f"DeepWiki unavailable (HTTP {response.status_code})"
            data = response.json()
            if "error" in data:
                logger.warning(f"DeepWiki RPC error: {data['error']}")
                return f"DeepWiki error: {data['error'].get('message', 'unknown')}"
            return json.dumps(data.get("result", data))
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
