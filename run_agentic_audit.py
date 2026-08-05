#!/usr/bin/env python3
"""Agentic batch audit — agent receives DeepWiki overview, then decides
which files to inspect using an interactive READ: protocol.
"""
import json, os, re, sys, time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app/mjolnir"))

from openai import OpenAI
import httpx

ROOCODE_HEADERS = {
    "user-agent": "RooCode/3.34.8",
    "x-title": "Roo Code",
    "http-referer": "https://github.com/RooVetGit/Roo-Cline",
    "x-stainless-runtime-version": "v22.20.0",
    "x-stainless-runtime": "node",
    "x-stainless-arch": "x64",
    "x-stainless-os": "Linux",
    "x-stainless-lang": "js",
}

class _TX(httpx.HTTPTransport):
    def handle_request(self, r):
        for k, v in ROOCODE_HEADERS.items():
            r.headers[k] = v
        return super().handle_request(r)

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL"),
    max_retries=3,
    http_client=httpx.Client(transport=_TX(), timeout=httpx.Timeout(600, connect=10)),
)

from providers.deepwiki.client import DeepWikiClient
dw = DeepWikiClient("astroanax/opentitan-test")

CODE_DIR = os.path.expanduser("~/ches-akhi/ches-new/opentitan")
THREAT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "projects/opentitan/threat_model.md")
with open(THREAT_MODEL_PATH) as f:
    threat_model = f.read()

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs", "agentic_runs", time.strftime("%Y%m%d_%H%M%S"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

MODEL = "gpt-5.6-sol"

# ── Phase 0: Fetch DeepWiki overview ──────────────────────────────────────────
print("=== Phase 0: Fetching DeepWiki codebase overview ===")
overview = dw.ask_question(
    "Give a comprehensive overview of this OpenTitan fork: list ALL security "
    "hardware modules (AES, keymgr, CSRNG, entropy source, lifecycle controller, "
    "OTBN, ROM controller, flash controller, alert handler, security primitives, "
    "SRAM controller, HMAC, KMAC, OTP, RV_DM debug, DMA, RACL), their roles, "
    "trust boundaries, and interactions. What are the most security-critical "
    "subsystems and why?"
)
print(f"Overview: {len(overview)} chars\n")

# ── System prompt ─────────────────────────────────────────────────────────────
with open(os.path.join(os.path.dirname(__file__), "app/mjolnir/providers/genai/prompts/systemverilog_auditor.md")) as f:
    sv_prompt = f.read()

SYSTEM = sv_prompt + "\n\n" + threat_model + """

## Interactive Exploration Protocol

You are auditing an RTL codebase. You start with an architectural overview
(provided below). You can request to READ any file in the repository. You can
also raise DOUBT: questions about cross-file relationships.

Protocol:
- READ: <relative/path/to/file.sv>  → the orchestrator returns the file contents
- DOUBT: <specific question>         → the orchestrator queries repository context
- When you have found and analyzed enough, output a JSON object with your findings
  in this format: {"findings": [{"file": "...", "title": "...", "severity": "...",
  "location": "...", "description": "...", "recommendation": "..."}]}

Start by reading the most security-critical files first. Focus on:
1. AES S-Box (side-channel masking)
2. Key manager (key derivation, sideload, validity checks)
3. CSRNG / entropy source (randomness generation, health tests)
4. Lifecycle controller (state transitions, debug gating)
5. ROM / ROM_EXT (signature verification, boot policy)
6. Alert handler (escalation paths)
7. Security primitives (alert sender/receiver, scrambling)

For each file you read, trace the security-critical signals across module
boundaries. If a finding depends on upstream or downstream behavior, DOUBT:
whether the mitigation exists elsewhere before reporting."""

# ── Messages ──────────────────────────────────────────────────────────────────
messages = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": f"CODEBASE OVERVIEW:\n\n{overview}\n\n"
                                 "Begin your security audit. Start by requesting "
                                 "the most security-critical files. Use READ: "
                                 "to request files and DOUBT: for cross-file questions."},
]

# ── Tool implementations ──────────────────────────────────────────────────────
def read_file(path: str) -> str:
    full = os.path.join(CODE_DIR, path)
    if not os.path.exists(full):
        return f"ERROR: File '{path}' not found."
    with open(full, errors="ignore") as f:
        return f.read()

def ask_dw(question: str) -> str:
    return dw.ask_question(question)

def call_llm(msgs):
    r = client.chat.completions.create(model=MODEL, messages=msgs)
    return r.choices[0].message.content or ""

def extract_json(text: str):
    """Extract JSON object from text that may have surrounding prose."""
    import re
    for m in re.finditer(r'\{[^{}]*"findings"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL):
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            continue
    for m in re.finditer(r'\{.*\}', text, re.DOTALL):
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            continue
    return None

# ── Agent loop ────────────────────────────────────────────────────────────────
MAX_TURNS = 15
files_read = []
all_findings = []
turn_log = []

for turn in range(MAX_TURNS):
    print(f"\n--- Turn {turn + 1}/{MAX_TURNS} ---")
    response = call_llm(messages)
    messages.append({"role": "assistant", "content": response})
    turn_log.append({"turn": turn + 1, "assistant": response})

    # Check for READ: requests
    read_matches = list(re.finditer(r'READ:\s*(\S+)', response))
    doubt_matches = list(re.finditer(r'DOUBT:\s*(.+?)(?=\n(?:READ:|DOUBT:|$))', response, re.DOTALL))

    if read_matches:
        for m in read_matches:
            fpath = m.group(1).strip()
            print(f"  Agent requests: {fpath}")
            content = read_file(fpath)
            files_read.append(fpath)
            messages.append({
                "role": "user",
                "content": f"FILE: {fpath}\n\n```\n{content[:8000]}\n```\n\n"
                           f"Continue your analysis."
            })
            turn_log[-1]["file_requested"] = fpath
            turn_log[-1]["file_length"] = len(content)
        continue

    if doubt_matches:
        for m in doubt_matches:
            question = m.group(1).strip()
            print(f"  Agent doubts: {question[:80]}...")
            answer = ask_dw(question)
            messages.append({
                "role": "user",
                "content": f"CONTEXT for your doubt:\n\n{answer}\n\nContinue your analysis."
            })
            turn_log[-1]["doubt"] = question
            turn_log[-1]["doubt_response"] = answer[:500]
        continue

    # No READ: or DOUBT: — try to extract findings JSON
    result = extract_json(response)
    if result and "findings" in result:
        print(f"  Agent produced final findings: {len(result['findings'])} issue(s)")
        all_findings = result["findings"]
        break

    # If we can't parse findings, push harder
    print("  No findings produced yet, pushing for output...")
    messages.append({
        "role": "user",
        "content": "You have read several files. Now PRODUCE YOUR FINDINGS. "
                   "Output a JSON object: {\"findings\": [{\"file\": \"...\", "
                   "\"title\": \"...\", \"severity\": \"...\", \"location\": \"...\", "
                   "\"description\": \"...\", \"recommendation\": \"...\"}]}. "
                   "Do not request more files. Output findings for what you have already analyzed."
    })

else:
    print(f"\nMAX_TURNS ({MAX_TURNS}) reached. Forcing final output.")
    messages.append({
        "role": "user",
        "content": "MAX_TURNS reached. Output your findings NOW as JSON: "
                   "{\"findings\": [...]} with all issues discovered so far."
    })
    final = call_llm(messages)
    result = extract_json(final)
    if result:
        all_findings = result.get("findings", [])

# ── Save results ──────────────────────────────────────────────────────────────
out = {
    "files_read": files_read,
    "findings": all_findings,
    "turns": len(turn_log),
    "turn_log": turn_log,
}

out_path = os.path.join(OUTPUT_DIR, "result.json")
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, default=str)

print(f"\n=== Done ===")
print(f"Files read: {len(files_read)}")
print(f"Findings: {len(all_findings)}")
print(f"Turns used: {len(turn_log)}")
print(f"Output: {out_path}")
for f in files_read:
    print(f"  - {f}")
for finding in all_findings:
    print(f"  [{finding.get('severity', '?')}] {finding.get('title', '?')[:80]} ({finding.get('file', '?')})")
