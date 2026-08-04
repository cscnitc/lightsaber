"""Base agent for OpenAI-compatible chat completions."""
import json

from utilities.logger import logger


class OpenAIMjolnirAgent:
    def __init__(self, client, model: str, system_instruction: str = ""):
        self.client = client
        self.model = model
        self.system_instruction = system_instruction
        self._max_tool_rounds = 10

    def _build_messages(self, user_content: str) -> list:
        messages = []
        if self.system_instruction:
            messages.append({"role": "system", "content": self.system_instruction})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _generate(self, messages, response_schema=None, tools=None):
        kwargs = {"model": self.model, "messages": messages}
        if response_schema:
            schema = response_schema.model_json_schema()
            schema_json = json.dumps(schema)
            messages = list(messages)
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += (
                    f"\n\nRespond ONLY with valid JSON matching this schema:\n{schema_json}"
                )
            kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return self.client.chat.completions.create(**kwargs)

    def _run_tool_loop(self, messages, tools, tool_handlers):
        for _round in range(self._max_tool_rounds):
            response = self._generate(messages, tools=tools)
            msg = response.choices[0].message
            if msg.content:
                return msg.content
            if msg.tool_calls:
                messages.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    } for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    handler = tool_handlers.get(name)
                    result = handler(**args) if handler else f"Error: Unknown tool '{name}'"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
            else:
                return ""
        return ""

    @staticmethod
    def get_response_text(response):
        if hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content or ""
        return ""
