#!/usr/bin/env python3
"""Batch audit top priority OpenTitan files through Mjolnir OpenAI provider."""
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app/mjolnir"))

from providers.openai.client import get_client
from providers.openai.agents.auditor import OpenAIAuditorAgent
from providers.deepwiki.client import DeepWikiClient, DeepWikiContextStatus

CODE_DIR = os.path.expanduser("~/ches-akhi/ches-new/opentitan")
THREAT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "projects/opentitan/threat_model.md"
)

# Tier 1 critical files — highest vulnerability probability
FILES = [
    # HARDWARE CRYPTO
    "hw/ip/aes/rtl/aes_sbox_dom.sv",
    "hw/ip/aes/rtl/aes_core.sv",
    "hw/ip/aes/rtl/aes_cipher_core.sv",
    "hw/ip/aes/rtl/aes_control_fsm.sv",
    "hw/ip/aes/rtl/aes_key_expand.sv",
    "hw/ip/aes/rtl/aes_prng_masking.sv",
    # KEY MANAGEMENT
    "hw/ip/keymgr/rtl/keymgr_ctrl.sv",
    "hw/ip/keymgr/rtl/keymgr.sv",
    "hw/ip/keymgr/rtl/keymgr_kmac_if.sv",
    "hw/ip/keymgr_dpe/rtl/keymgr_dpe.sv",
    "hw/ip/keymgr_dpe/rtl/keymgr_dpe_ctrl.sv",
    # ENTROPY / RNG
    "hw/ip/csrng/rtl/csrng_core.sv",
    "hw/ip/csrng/rtl/csrng_ctr_drbg_upd.sv",
    "hw/ip/csrng/rtl/csrng_ctr_drbg_gen.sv",
    "hw/ip/entropy_src/rtl/entropy_src_core.sv",
    "hw/ip/edn/rtl/edn_core.sv",
    # LIFECYCLE
    "hw/ip/lc_ctrl/rtl/lc_ctrl_fsm.sv",
    "hw/ip/lc_ctrl/rtl/lc_ctrl.sv",
    # OTBN
    "hw/ip/otbn/rtl/otbn_controller.sv",
    "hw/ip/otbn/rtl/otbn.sv",
    # ROM / BOOT
    "sw/device/silicon_creator/rom/rom.c",
    "sw/device/silicon_creator/rom/sigverify_otp_keys.c",
    "sw/device/silicon_creator/rom_ext/rom_ext.c",
    # SIGVERIFY
    "sw/device/silicon_creator/lib/sigverify/mod_exp_ibex.c",
    "sw/device/silicon_creator/lib/sigverify/rsa_verify.c",
    "sw/device/silicon_creator/lib/sigverify/ecdsa_p256_verify.c",
    # DICE / ATTESTATION
    "sw/device/silicon_creator/lib/cert/dice_chain.c",
    "sw/device/silicon_creator/lib/cert/dice_cwt.c",
    # OWNERSHIP
    "sw/device/silicon_creator/lib/ownership/ownership.c",
    "sw/device/silicon_creator/lib/ownership/ownership_unlock.c",
    # FLASH / BOOT DATA
    "sw/device/silicon_creator/lib/drivers/flash_ctrl.c",
    "sw/device/silicon_creator/lib/boot_data.c",
    "sw/device/silicon_creator/lib/bootstrap.c",
    "sw/device/silicon_creator/lib/shutdown.c",
    # SECURITY PRIMITIVES
    "hw/ip/prim/rtl/prim_alert_sender.sv",
    "hw/ip/prim/rtl/prim_alert_receiver.sv",
    "hw/ip/prim/rtl/prim_ram_1p_scr.sv",
]

with open(THREAT_MODEL_PATH) as f:
    threat_model = "\n\n" + f.read()

client = get_client()
assert client, "OPENAI_API_KEY not set"

dw_client = DeepWikiClient("astroanax/opentitan-test")

def context_resolver(question: str) -> str:
    return dw_client.ask_question(question)

auditor = OpenAIAuditorAgent(
    client, "gpt-5.6-sol", threat_model,
    context_resolver=context_resolver,
)

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "outputs", "raw_outputs", time.strftime("%Y%m%d_%H%M%S")
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

all_vulnerabilities = []
all_metadata = []
started = time.time()

for i, f_path in enumerate(FILES):
    full_path = os.path.join(CODE_DIR, f_path)
    if not os.path.exists(full_path):
        print(f"[{i+1}/{len(FILES)}] SKIP {f_path} — not found")
        continue

    with open(full_path, errors="ignore") as f:
        contents = f.read()

    lines = len(contents.splitlines())
    print(f"[{i+1}/{len(FILES)}] {f_path} ({lines} lines)...", end=" ", flush=True)

    OUT_PATH = os.path.join(OUTPUT_DIR, f_path.replace("/", "_") + ".json")
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    try:
        report = auditor.run(f_path, contents)
    except Exception as e:
        print(f"FAILED: {e}")
        entry = {"file": f_path, "error": str(e), "status": "failed", "findings": []}
        all_metadata.append(entry)
        with open(OUT_PATH, "w") as f:
            json.dump(entry, f, indent=2, default=str)
        continue

    n = len(report.vulnerabilities)
    findings = []
    print(f"OK — {n} finding(s)")

    for finding in report.vulnerabilities:
        v = auditor._to_vulnerability(finding, f_path)
        v.add(phase_id="1", phase_name="Source File Exploration", finding=finding)
        findings.append(v.model_dump())

    entry = {
        "file": f_path,
        "lines": lines,
        "status": "success",
        "findings": findings,
    }
    all_metadata.append(entry)

    # Write per-file output
    with open(OUT_PATH, "w") as f:
        json.dump(entry, f, indent=2, default=str)

elapsed = int(time.time() - started)
print(f"\n=== Done in {elapsed}s ===")
success = [e for e in all_metadata if e["status"] == "success"]
failed = [e for e in all_metadata if e["status"] == "failed"]
total_findings = sum(len(e["findings"]) for e in success)
print(f"Successful: {len(success)}, Failed: {len(failed)}, Findings: {total_findings}")

# Write summary
summary = {
    "metadata": {
        "files_scanned": len(FILES),
        "successful": len(success),
        "failed": len(failed),
        "total_findings": total_findings,
        "duration_seconds": elapsed,
        "model": "gpt-5.6-sol",
    },
    "results": all_metadata,
}
summary_path = os.path.join(OUTPUT_DIR, "_summary.json")
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(f"\nOutput: {OUTPUT_DIR}/")
