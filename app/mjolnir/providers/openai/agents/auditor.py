"""OpenAI-compatible auditor agent with language-specific prompt resolution.

Supports multi-turn doubt resolution: the agent can output DOUBT: <question>
and the orchestrator routes it to a context provider (e.g., DeepWiki MCP)
for cross-file context, then feeds the response back. Max 10 doubt turns
before the orchestrator forces a final answer.
"""
from pathlib import Path

from data.security_report import SecurityReport
from providers.openai.agents.base import OpenAIMjolnirAgent
from providers.openai.agents.doubt_loop import run_with_doubts
from utilities.logger import logger

EXTENSION_TO_PROMPT = {
    "c": "c_auditor.md",
    "h": "c_auditor.md",
    "cpp": "c_auditor.md",
    "cc": "c_auditor.md",
    "rs": "rust_auditor.md",
    "sv": "systemverilog_auditor.md",
}
DEFAULT_PROMPT = "c_auditor.md"

DOUBT_INSTRUCTION = (
    "\n\nYou are auditing a single file. You DO NOT have direct access to the "
    "rest of the repository. If you need to understand cross-file relationships "
    "(callers, callees, upstream checks, downstream consumers, architectural "
    "invariants, error propagation paths, or integration behavior), raise a "
    "doubt using the following format on its own line:\n\n"
    "DOUBT: <your specific question about the repository>\n\n"
    "The orchestrator will fetch the answer from the repository context and "
    "return it to you. You can raise multiple doubts, but aim for targeted, "
    "specific questions. When you have enough context, produce your final "
    "SecurityReport JSON."
)


class OpenAIAuditorAgent(OpenAIMjolnirAgent):
    """Auditor with multi-turn doubt resolution for cross-file context."""

    def __init__(self, client, model: str, threat_model_context: str = "",
                 context_resolver=None):
        super().__init__(client, model)
        self.threat_model_context = threat_model_context
        self.context_resolver = context_resolver

    def _resolve_instruction(self, file_path: str) -> str:
        prompts_dir = Path(__file__).resolve().parent.parent.parent / "genai" / "prompts"
        ext = Path(file_path).suffix.lstrip(".").lower()
        if ext not in EXTENSION_TO_PROMPT:
            logger.warning(f"[API Warning] Unsupported extension .{ext}. Defaulting to C auditor.")
            prompt_name = DEFAULT_PROMPT
        else:
            prompt_name = EXTENSION_TO_PROMPT[ext]
        prompt_path = prompts_dir / prompt_name
        if prompt_path.exists():
            with open(prompt_path, encoding="utf-8") as f:
                base_prompt = f.read().strip()
            return base_prompt + self.threat_model_context + DOUBT_INSTRUCTION
        return "Analyze this file for potential security vulnerabilities." + self.threat_model_context

    def run(self, file_rel_path: str, contents: str) -> SecurityReport:
        logger.debug(f"Scanning {file_rel_path} (OpenAI)...")
        system_instruction = self._resolve_instruction(file_rel_path)
        user_content = (
            f"Analyze this file:\n\nFilename: {file_rel_path}\n\nContent:\n{contents}"
        )
        messages = self._build_messages(user_content)
        if system_instruction:
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] = system_instruction
            else:
                messages.insert(0, {"role": "system", "content": system_instruction})

        def _gen(msgs, response_schema=None):
            response = self._generate(msgs, response_schema=response_schema)
            return self.get_response_text(response)

        if self.context_resolver:
            output = run_with_doubts(
                _gen,
                messages,
                self.context_resolver,
                response_schema=SecurityReport,
            )
        else:
            output = _gen(messages, response_schema=SecurityReport)

        return SecurityReport.model_validate_json(output)

    @staticmethod
    def _to_vulnerability(finding, file_path: str):
        import uuid
        from data.vulnerability import Vulnerability
        return Vulnerability(
            id=str(uuid.uuid4()),
            file=file_path,
            title=finding.title,
            severity=finding.severity,
            location=finding.location,
            description=finding.description,
            recommendation=finding.recommendation,
        )
