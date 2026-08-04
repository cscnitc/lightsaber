"""Tests for OpenAI auditor agent prompt resolution."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from providers.openai.agents.auditor import OpenAIAuditorAgent


def test_auditor_resolves_sv_to_systemverilog_prompt():
    agent = OpenAIAuditorAgent(None, "test-model")
    instruction = agent._resolve_instruction("hw/ip/aes/rtl/aes_sbox_dom.sv")
    assert "SystemVerilog" in instruction
    assert "Hardware Security" in instruction
    assert "Fault Injection" in instruction
    assert "Secrets" in instruction or "Secret" in instruction


def test_auditor_resolves_c_to_c_prompt():
    agent = OpenAIAuditorAgent(None, "test-model")
    instruction = agent._resolve_instruction("sw/device/rom/rom.c")
    assert "SystemVerilog" not in instruction
    assert "C/C++" in instruction or "Firmware" in instruction


def test_auditor_resolves_unknown_extension_to_default_prompt():
    agent = OpenAIAuditorAgent(None, "test-model")
    instruction = agent._resolve_instruction("some/file.xyz")
    assert len(instruction) > 0
