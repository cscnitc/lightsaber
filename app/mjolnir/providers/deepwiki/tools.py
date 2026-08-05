"""DeepWiki MCP tools as OpenAI-compatible function definitions + handlers.

Wraps the DeepWikiClient JSON-RPC calls into callable functions and
OpenAI tool schemas so LLM agents can query repository context during
analysis — reading architecture docs, browsing wiki structure, and
asking clarifying questions about cross-module relationships.
"""
from providers.deepwiki.client import DeepWikiClient


def build_deepwiki_tool_definitions() -> list:
    """OpenAI-compatible tool schemas for DeepWiki MCP tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_wiki_structure",
                "description": (
                    "Get a list of documentation topics for the target repository. "
                    "Use this first to understand what architectural and security "
                    "documentation is available before asking specific questions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_wiki_contents",
                "description": (
                    "View full documentation about the repository. Use this when "
                    "you need deep architectural understanding of a component, its "
                    "trust boundaries, security invariants, and integration points."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_question",
                "description": (
                    "Ask any question about the repository and get an AI-powered "
                    "context-grounded answer. Use this to understand cross-module "
                    "relationships, caller/callee patterns, security invariants, "
                    "known hardening measures, error propagation paths, and "
                    "architectural intent. Ask specific, targeted questions about "
                    "the module you are auditing and its surrounding context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "A specific question about the repository. Be precise: "
                                "name modules, signals, or security properties."
                            ),
                        },
                    },
                    "required": ["question"],
                },
            },
        },
    ]


def build_deepwiki_tool_handlers(dw_client: DeepWikiClient) -> dict:
    """Callable handlers that invoke the DeepWiki MCP client."""
    def _read_structure() -> str:
        return dw_client.read_wiki_structure()

    def _read_contents() -> str:
        return dw_client.read_wiki_contents()

    def _ask(question: str) -> str:
        return dw_client.ask_question(question)

    return {
        "read_wiki_structure": _read_structure,
        "read_wiki_contents": _read_contents,
        "ask_question": _ask,
    }
