"""OpenAI-compatible API client."""
import os
import uuid

import httpx
from openai import OpenAI

from utilities.logger import logger

# Stable per-process session id. Gateways such as https://opencode.ai/zen/go/v1
# require an x-opencode-session header to route requests efficiently; without it
# they answer 400 MissingSessionID. Override with OPENAI_SESSION_ID when a
# specific session must be reused.
_SESSION_ID = os.environ.get("OPENAI_SESSION_ID") or str(uuid.uuid4())

ROOCODE_HEADERS = {
    "user-agent": "RooCode/3.34.8",
    "x-title": "Roo Code",
    "http-referer": "https://github.com/RooVetGit/Roo-Cline",
    "x-opencode-session": _SESSION_ID,
    "x-stainless-runtime-version": "v22.20.0",
    "x-stainless-runtime": "node",
    "x-stainless-arch": "x64",
    "x-stainless-os": "Linux",
    "x-stainless-lang": "js",
}


class _InjectHeadersTransport(httpx.HTTPTransport):
    def handle_request(self, request):
        for key, value in ROOCODE_HEADERS.items():
            request.headers[key] = value
        return super().handle_request(request)


def get_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set.")
        return None
    base_url = os.environ.get("OPENAI_BASE_URL")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    transport = _InjectHeadersTransport()
    http_client = httpx.Client(transport=transport, timeout=httpx.Timeout(600.0, connect=10.0))
    return OpenAI(max_retries=3, http_client=http_client, **kwargs)
