"""OpenAI-compatible auditor agent with language-specific prompt resolution."""
from pathlib import Path

from data.security_report import SecurityReport
from providers.openai.agents.base import OpenAIMjolnirAgent
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


class OpenAIAuditorAgent(OpenAIMjolnirAgent):
    """Dynamic auditor that resolves language prompts and audits code files."""

    def __init__(self, client, model: str, threat_model_context: str = ""):
        super().__init__(client, model)
        self.threat_model_context = threat_model_context

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
            return base_prompt + self.threat_model_context
        return "Analyze this file for potential security vulnerabilities." + self.threat_model_context

    def run(self, file_rel_path: str, contents: str) -> SecurityReport:
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
        response = self._generate(messages, response_schema=SecurityReport)
        return SecurityReport.model_validate_json(self.get_response_text(response))

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
