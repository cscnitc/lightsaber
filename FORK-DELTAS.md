# Lightsaber vs upstream Mjolnir — file-by-file delta

Upstream: [chipsalliance/mjolnir](https://github.com/chipsalliance/mjolnir),
commit `2a0ba9e`. Everything under `flake.nix`, `nix/`, `projects/*/nix`,
`BUILD.bazel`/`MODULE.bazel` job packaging, and the Gemini/Vertex providers
(`app/mjolnir/providers/genai/`, `app/mjolnir/providers/adk/`) is inherited
upstream and untouched in purpose. The five Lightsaber additions below are
what the P2 runs used; none of them exists upstream.

1. OpenAI-compatible provider — `app/mjolnir/providers/openai/`
   (`client.py`, `main.py`, `agents/base.py`, `agents/auditor.py`,
   `agents/doubt_loop.py`, `agents/adversarial_reviewer.py`).
   Speaks the Responses API (`client.responses.create`, JSON-schema
   structured output, `previous_response_id` tool state) against any
   OpenAI-compatible endpoint via `OPENAI_API_KEY` + `OPENAI_BASE_URL`.
   Upstream only speaks Gemini/Vertex. P2 runs: AgentRouter
   (`agentrouter.org/v1`), Zen chat, Go responses gateways.

2. SystemVerilog auditor prompt —
   `app/mjolnir/providers/genai/prompts/systemverilog_auditor.md`,
   wired in via `EXTENSION_TO_PROMPT` (`auditor.py`: `.sv` →
   `systemverilog_auditor.md`). Upstream has C/Rust prompts only and
   falls back to the C auditor for `.sv`; the Lightsaber prompt covers
   fault injection and hardened FSMs, secret handling and remanence,
   masking/DOM side channels, reset/clock/CDC, access control,
   width/index hazards, entropy and crypto control, alerts/escalation.

3. Evidence levels + DeepWiki tracking — finding schema gains E0–E5
   confidence levels and per-finding `deepwiki_context_status` /
   `deepwiki_verified` / `deepwiki_queries` fields, so a cross-file claim
   records whether repository context was consulted.

4. DeepWiki MCP integration — `app/mjolnir/providers/deepwiki/`
   (`client.py`, `tools.py`): `read_wiki_structure` / `read_wiki_contents`
   / `ask_question` over `https://mcp.deepwiki.com/mcp`. Both run scripts
   resolve cross-file questions through it before filing findings.

5. Agentic runs — `run_agentic_audit.py` (READ:/DOUBT: loop: the agent
   requests files and raises cross-file DOUBT questions iteratively,
   crash-proof per-turn `result.json` autosave) and `run_batch_audit.py`
   (shortlist batch driver with per-file DOUBT resolution). Both take
   `--tree` (default `/opt/opentitan`), `--model`, `--output-dir`,
   `--deepwiki-repo`; the agentic script adds `--focus` and `--max-turns`,
   the batch script adds `--files`. Every run dir is self-logging:
   `result.json` / `_summary.json` carry tool name, run ID, model, tree,
   target commit (`git rev-parse`), file list, prompt reference
   (`SYSTEM_PROMPT.md` for agentic runs), and token totals; no API keys
   are ever written.

## One-command repro (B-001, flash shortlist200)

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="<your-key>" OPENAI_BASE_URL="https://agentrouter.org/v1"
python3 run_batch_audit.py --tree /opt/opentitan --model deepseek-v4-flash \
    --files <shortlist-200.txt>
# expect: aes_control_fsm.sv finding naming the unreachable CTRL_CLEAR_I wipe
# state; run dir _summary.json holds model/run ID/commit/tokens.
```

P2 campaign records (models, run IDs, metered token totals, per-bug finding
JSONs) are in each submission pack's `*-llm-logs.zip`.
