"""Base agent supporting both OpenAI chat-completions and responses protocols.

Protocol selection via the MJOLNIR_OPENAI_PROTOCOL environment variable:
  chat       - client.chat.completions.create (default, unchanged behavior)
  responses  - client.responses.create (for models such as
               muse-spark-1.3-contributor on https://opencode.ai/zen/go/v1,
               which do not implement the chat protocol)

Token budget via MJOLNIR_MAX_OUTPUT_TOKENS (default 16384).
"""
import json
import os
import re

from providers.openai.usage import record
from utilities.logger import logger

PROTOCOL = os.environ.get("MJOLNIR_OPENAI_PROTOCOL", "chat").lower()
try:
    MAX_OUTPUT_TOKENS = int(os.environ.get("MJOLNIR_MAX_OUTPUT_TOKENS", "16384"))
except ValueError:
    MAX_OUTPUT_TOKENS = 16384


def _protocol() -> str:
    """Read protocol dynamically so env changes after import take effect."""
    return os.environ.get("MJOLNIR_OPENAI_PROTOCOL", "chat").lower()


def _max_output_tokens() -> int:
    try:
        return int(os.environ.get("MJOLNIR_MAX_OUTPUT_TOKENS", "16384"))
    except ValueError:
        return 16384


def _describe_response_shape(response) -> str:
    """One-line shape summary for logging when a call yields no text."""
    try:
        if getattr(response, "choices", None):
            msg = response.choices[0].message
            fields = {}
            for f in ("content", "reasoning_content", "reasoning", "refusal",
                      "role", "tool_calls", "function_call"):
                try:
                    v = getattr(msg, f, None)
                except Exception:
                    v = None
                if v is None:
                    continue
                fields[f] = len(v) if isinstance(v, (str, list)) else type(v).__name__
            finish = getattr(response.choices[0], "finish_reason", None)
            usage = getattr(response, "usage", None)
            u = ""
            if usage is not None:
                u = (f", usage(prompt={getattr(usage, 'prompt_tokens', '?')}, "
                     f"completion={getattr(usage, 'completion_tokens', '?')})")
            return f"chat finish_reason={finish} msg_fields={fields}{u}"
        out = getattr(response, "output", None) or []
        types = [(_item_type(i)) for i in out]
        status = getattr(response, "status", None)
        usage = getattr(response, "usage", None)
        u = ""
        if usage is not None:
            u = (f", usage(input={getattr(usage, 'input_tokens', '?')}, "
                 f"output={getattr(usage, 'output_tokens', '?')})")
        return f"responses status={status} output_types={types}{u}"
    except Exception as e:
        return f"<shape-unavailable: {e}>"


def _record_usage(model: str, phase: str, response, chat: bool) -> None:
    """Record token usage for one raw response (chat or responses shape)."""
    try:
        usage = response.usage
        if chat:
            record(
                model, phase,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        else:
            record(
                model, phase,
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )
    except Exception:
        pass


def _schema_suffix(response_schema) -> str:
    schema_json = json.dumps(response_schema.model_json_schema())
    return f"\n\nRespond ONLY with valid JSON matching this schema:\n{schema_json}"


def _split_messages(messages):
    """Split a chat message list into (instructions, input_items) for responses."""
    instructions = ""
    items = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system" and not instructions:
            instructions = content
        elif role == "user":
            items.append({"role": "user", "content": content})
        elif role == "assistant" and content:
            items.append({"role": "assistant", "content": content})
        # chat-native tool_calls/tool messages have no responses equivalent
        # mid-conversation; they are handled by the responses tool loop instead.
    return instructions, items


def _chat_tools_to_responses(tools):
    """Convert chat function tools to responses function tools."""
    out = []
    for t in tools or []:
        fn = t.get("function", t) if isinstance(t, dict) else t
        if not isinstance(fn, dict):
            continue
        out.append(
            {
                "type": "function",
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                "strict": False,
            }
        )
    return out


def _item_type(item) -> str:
    if isinstance(item, dict):
        return item.get("type", "")
    return getattr(item, "type", "")


def _dump_output_item(item):
    """Serialize a responses output item to a plain dict for re-submission."""
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        try:
            return item.model_dump(exclude_none=True)
        except Exception:
            pass
    if hasattr(item, "__dict__"):
        try:
            return dict(item.__dict__)
        except Exception:
            pass
    return dict(item)


def parse_schema_json(text, model):
    """Validate text as model JSON, tolerating prose/markdown fences around it.

    Tries direct validation, then scans for the largest {...} span that parses
    and validates (handles models that narrate before/after the JSON payload).
    """
    import json as _json

    from pydantic import ValidationError

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
    try:
        return model.model_validate_json(cleaned)
    except (ValueError, ValidationError):
        pass
    best = None
    decoder = _json.JSONDecoder()
    for m in re.finditer(r"\{", cleaned):
        try:
            obj, _ = decoder.raw_decode(cleaned[m.start():])
        except ValueError:
            continue
        try:
            candidate = model.model_validate(obj)
        except ValidationError:
            continue
        if best is None or len(str(obj)) > len(str(best[0])):
            best = (obj, candidate)
    if best is not None:
        return best[1]
    return model.model_validate_json(text)


class OpenAIMjolnirAgent:
    def __init__(self, client, model: str, system_instruction: str = ""):
        self.client = client
        self.model = model
        self.system_instruction = system_instruction
        self._max_tool_rounds = 10
        self._phase = ""

    def _build_messages(self, user_content: str) -> list:
        messages = []
        if self.system_instruction:
            messages.append({"role": "system", "content": self.system_instruction})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _generate(self, messages, response_schema=None, tools=None):
        if _protocol() == "responses":
            return self._generate_responses(messages, response_schema, tools)
        kwargs = {"model": self.model, "messages": messages}
        if response_schema:
            messages = list(messages)
            if messages and messages[-1]["role"] == "user":
                messages[-1]["content"] += _schema_suffix(response_schema)
            kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = self.client.chat.completions.create(**kwargs)
        try:
            _has_tools = bool(getattr(response.choices[0].message, "tool_calls", None))
        except Exception:
            _has_tools = False
        if not _has_tools and not self.get_response_text(response):
            # Empty content (e.g. reasoning models emitting only
            # reasoning_content, or a truncated/refused call): log the raw
            # shape and retry once before giving up on this call.
            logger.warning(
                f"[chat] empty output, retrying once. shape={_describe_response_shape(response)}"
            )
            _record_usage(self.model, self._phase, response, chat=True)
            response = self.client.chat.completions.create(**kwargs)
            if not self.get_response_text(response):
                logger.warning(
                    f"[chat] empty output after retry. shape={_describe_response_shape(response)}"
                )
        try:
            usage = response.usage
            record(
                self.model,
                self._phase,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        except Exception:
            pass
        return response

    def _generate_responses(self, messages, response_schema=None, tools=None):
        instructions, items = _split_messages(messages)
        if response_schema and items:
            last = dict(items[-1])
            last["content"] += _schema_suffix(response_schema)
            items[-1] = last
        kwargs = {
            "model": self.model,
            "instructions": instructions or None,
            "input": items,
            "max_output_tokens": _max_output_tokens(),
        }
        if response_schema:
            try:
                kwargs["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": response_schema.__name__,
                        "schema": response_schema.model_json_schema(),
                        "strict": False,
                    }
                }
            except Exception as e:
                logger.warning(f"[responses] skipping json_schema format: {e}")
        resp_tools = _chat_tools_to_responses(tools)
        if resp_tools:
            kwargs["tools"] = resp_tools
            kwargs["tool_choice"] = "auto"
        response = self.client.responses.create(**kwargs)
        _has_calls = any(
            _item_type(i) == "function_call" for i in (getattr(response, "output", None) or [])
        )
        if not _has_calls and not self.get_response_text(response):
            logger.warning(
                f"[responses] empty output, retrying once. shape={_describe_response_shape(response)}"
            )
            _record_usage(self.model, self._phase, response, chat=False)
            response = self.client.responses.create(**kwargs)
            if not self.get_response_text(response):
                logger.warning(
                    f"[responses] empty output after retry. shape={_describe_response_shape(response)}"
                )
        try:
            usage = response.usage
            record(
                self.model,
                self._phase,
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )
        except Exception:
            pass
        return response

    def _run_tool_loop(self, messages, tools, tool_handlers):
        if _protocol() == "responses":
            return self._run_tool_loop_responses(messages, tools, tool_handlers)
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

    def _run_tool_loop_responses(self, messages, tools, tool_handlers):
        instructions, items = _split_messages(messages)
        resp_tools = _chat_tools_to_responses(tools)
        for _round in range(self._max_tool_rounds):
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions or None,
                input=items,
                tools=resp_tools,
                tool_choice="auto",
                max_output_tokens=_max_output_tokens(),
            )
            try:
                usage = response.usage
                record(
                    self.model,
                    self._phase,
                    getattr(usage, "input_tokens", 0) or 0,
                    getattr(usage, "output_tokens", 0) or 0,
                )
            except Exception:
                pass
            text = self.get_response_text(response)
            calls = [
                item for item in (response.output or [])
                if _item_type(item) == "function_call"
            ]
            if not calls:
                return text
            for item in response.output or []:
                try:
                    items.append(_dump_output_item(item))
                except Exception:
                    pass
            for call in calls:
                if isinstance(call, dict):
                    name = call.get("name", "")
                    raw_args = call.get("arguments", "") or "{}"
                    call_id = call.get("call_id", "")
                else:
                    name = getattr(call, "name", "")
                    raw_args = getattr(call, "arguments", "") or "{}"
                    call_id = getattr(call, "call_id", "")
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                handler = tool_handlers.get(name)
                try:
                    result = handler(**args) if handler else f"Error: Unknown tool '{name}'"
                except TypeError as e:
                    result = f"Error calling tool '{name}': {e}"
                items.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": str(result),
                })
        return self.get_response_text(response)

    @staticmethod
    def get_response_text(response):
        if hasattr(response, "choices") and response.choices:
            msg = response.choices[0].message
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                # Some gateways (e.g. opencode zen) return structured content
                # parts: [{'type': 'text', 'text': ...}, {'type': 'thinking', ...}].
                # Keep human-visible text, drop thinking blocks.
                texts = []
                for part in content:
                    if isinstance(part, str):
                        texts.append(part)
                    elif isinstance(part, dict):
                        if part.get("type") == "text" and part.get("text"):
                            texts.append(part["text"])
                    else:
                        try:
                            t = getattr(part, "text", None)
                            ptype = getattr(part, "type", "text")
                            if t and ptype == "text":
                                texts.append(t)
                        except Exception:
                            pass
                content = "".join(texts)
            if content:
                return content
            # Reasoning-distilled models may place output outside content.
            for f in ("reasoning_content", "reasoning", "refusal"):
                try:
                    v = getattr(msg, f, None)
                except Exception:
                    v = None
                if v:
                    return v if isinstance(v, str) else str(v)
            return ""
        if getattr(response, "output_text", None):
            try:
                return response.output_text or ""
            except Exception:
                pass
        # Fallback: scan responses output items (SDK variants lacking output_text).
        try:
            parts = []
            for item in getattr(response, "output", None) or []:
                if isinstance(item, dict):
                    itype = item.get("type", "")
                    content = item.get("content", None)
                else:
                    itype = getattr(item, "type", "")
                    content = getattr(item, "content", None)
                if itype == "message":
                    for block in content or []:
                        if isinstance(block, dict):
                            btype = block.get("type", "")
                            btext = block.get("text", "")
                        else:
                            btype = getattr(block, "type", "")
                            btext = getattr(block, "text", "")
                        if btype in ("output_text", "text"):
                            parts.append(btext or "")
                elif itype == "output_text":
                    if isinstance(item, dict):
                        parts.append(item.get("text", "") or "")
                    else:
                        parts.append(getattr(item, "text", "") or "")
            if parts:
                return "".join(parts)
        except Exception:
            pass
        return ""
