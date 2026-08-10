#!/usr/bin/env python3
"""Offline regression for the Windows/Clash/Mihomo SSH transport planner."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLANNER = ROOT / "scripts" / "plan_windows_ssh_transport.py"
FINGERPRINT = "SHA256:" + base64.b64encode(b"f" * 32).decode("ascii").rstrip("=")
NEGATIVE_CASES = 0


def canonical_sha(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def direct_evidence(status: str) -> dict:
    evidence: dict = {"classification": status}
    if status == "success":
        evidence.update({"openssh_exit_code": 0, "host_key_verified": True})
    elif status == "banner_timeout":
        evidence.update({"tcp_connected": True, "ssh_banner_received": False})
    elif status == "fake_ip":
        evidence.update({
            "system_answer": "198.18.0.7",
            "doh_answer": "198.51.100.7",
            "system_answer_is_fake_ip": True,
            "answers_differ": True,
        })
    elif status == "tun_interference":
        evidence.update({"tun_interface_observed": True, "route_snapshot_sha256": "c" * 64})
    return evidence


def load_planner():
    spec = importlib.util.spec_from_file_location("windows_ssh_planner", PLANNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("planner import spec unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def base_payload(status: str = "success") -> dict:
    evidence = direct_evidence(status)
    return {
        "schema_version": 1,
        "session_id": "closeout-task-001",
        "target": {
            "hostname": "connect.example.invalid",
            "port": 23456,
            "user": "root",
            "identity_file": "C:/keys/id_ed25519",
        },
        "timeouts": {"connect_seconds": 15, "banner_seconds": 20},
        "direct_openssh": {
            "status": status,
            "evidence": evidence,
            "evidence_sha256": canonical_sha(evidence),
        },
        "host_key": {
            "mode": "pinned",
            "fingerprint": FINGERPRINT,
            "known_hosts_file": "C:/session/known_hosts",
        },
    }


def fallback_payload(status: str = "banner_timeout") -> dict:
    payload = base_payload(status)
    response = {"answers": ["198.51.100.7", "198.51.100.8"]}
    payload["doh"] = {
        "resolver_url": "https://resolver.example/dns-query",
        "hostname": "connect.example.invalid",
        "observed_at": "2026-08-10T00:00:00Z",
        "response": response,
        "response_sha256": canonical_sha(response),
        "selected_ip": "198.51.100.7",
    }
    payload["windows"] = {"interface_index": 23}
    receipt = {
        "session_id": "closeout-task-001",
        "logical_hostname": "connect.example.invalid",
        "port": 23456,
        "selected_ip": "198.51.100.7",
        "key_type": "ssh-ed25519",
        "fingerprint": FINGERPRINT,
        "observed_at": "2026-08-10T00:00:00Z",
        "direct_evidence_sha256": payload["direct_openssh"]["evidence_sha256"],
        "first_contact_mitm_unavailable": True,
        "doh_response_sha256": payload["doh"]["response_sha256"],
    }
    payload["host_key"] = {
        "mode": "session_tofu",
        "fingerprint": FINGERPRINT,
        "receipt_path": "C:/session/tofu-receipt.json",
        "known_hosts_file": "C:/session/known_hosts",
        "receipt": receipt,
        "receipt_sha256": canonical_sha(receipt),
    }
    return payload


def direct_tofu_payload() -> dict:
    payload = base_payload()
    receipt = {
        "session_id": "closeout-task-001",
        "logical_hostname": "connect.example.invalid",
        "port": 23456,
        "key_type": "ssh-ed25519",
        "fingerprint": FINGERPRINT,
        "observed_at": "2026-08-10T00:00:00Z",
        "direct_evidence_sha256": payload["direct_openssh"]["evidence_sha256"],
        "first_contact_mitm_unavailable": True,
    }
    payload["host_key"] = {
        "mode": "session_tofu",
        "fingerprint": FINGERPRINT,
        "receipt_path": "C:/session/tofu-receipt.json",
        "known_hosts_file": "C:/session/known_hosts",
        "receipt": receipt,
        "receipt_sha256": canonical_sha(receipt),
    }
    return payload


def expect_error(module, payload: dict, marker: str) -> None:
    global NEGATIVE_CASES
    try:
        module.build_plan(payload)
    except module.PlanError as exc:
        assert marker in str(exc), (marker, str(exc))
    else:
        raise AssertionError(f"expected PlanError containing {marker!r}")
    NEGATIVE_CASES += 1


def main() -> int:
    if not PLANNER.is_file():
        print("[FAIL] offline Windows SSH transport contract: planner missing")
        return 1
    source = PLANNER.read_text(encoding="utf-8")
    for forbidden in (
        "import socket", "import paramiko", "from paramiko", "subprocess", "requests", "urllib.request",
        "urlopen", "http.client",
    ):
        assert forbidden not in source, f"planner must remain offline: {forbidden}"

    module = load_planner()
    direct = module.build_plan(base_payload())
    assert direct["transport"] == "openssh_direct"
    assert direct["host_key"]["strict"] is True
    assert direct["system_mutations"] == []
    assert module.build_plan(direct_tofu_payload())["transport"] == "openssh_direct"

    for status in ("banner_timeout", "fake_ip", "tun_interference"):
        fallback = module.build_plan(fallback_payload(status))
        assert fallback["transport"] == "paramiko_single_socket"
        assert fallback["connect_host"] == "198.51.100.7"
        assert fallback["windows_socket"]["option"] == "IP_UNICAST_IF"
        assert fallback["windows_socket"]["interface_index"] == 23
        assert fallback["host_key"]["mode"] == "session_tofu"
        assert fallback["system_mutations"] == []
        assert fallback["reporting_gate"] == {
            "fallback_attempt_required": True,
            "premature_transport_block_forbidden": True,
            "remote_state_inference_allowed": False,
            "terminal_transport_verdict_requires": "bounded fallback attempt or host identity gate",
        }

    for status in ("auth_failed", "host_key_mismatch", "connection_refused", "other_error"):
        expect_error(module, fallback_payload(status), "fallback_not_authorized")

    missing_doh = fallback_payload()
    missing_doh.pop("doh")
    expect_error(module, missing_doh, "doh")

    wrong_doh_host = fallback_payload()
    wrong_doh_host["doh"]["hostname"] = "other.example.invalid"
    expect_error(module, wrong_doh_host, "doh.hostname_mismatch")

    bad_interface = fallback_payload()
    bad_interface["windows"]["interface_index"] = 0
    expect_error(module, bad_interface, "interface_index")

    huge_interface = fallback_payload()
    huge_interface["windows"]["interface_index"] = 2**40
    expect_error(module, huge_interface, "interface_index")

    missing_receipt = fallback_payload()
    missing_receipt["host_key"].pop("receipt_path")
    expect_error(module, missing_receipt, "receipt_path")

    for global_known_hosts in (
        "~/.ssh/known_hosts",
        "%USERPROFILE%\\.ssh\\known_hosts",
        "C:/Users/fixture/.ssh/known_hosts",
        "/home/fixture/.ssh/known_hosts",
    ):
        user_global = fallback_payload()
        user_global["host_key"]["known_hosts_file"] = global_known_hosts
        expect_error(module, user_global, "known_hosts_file_must_not_be_user_global")

    outside_session = fallback_payload()
    outside_session["host_key"]["known_hosts_file"] = "C:/other/known_hosts"
    expect_error(module, outside_session, "known_hosts_file_must_be_session_scoped")

    direct_tofu_global = direct_tofu_payload()
    direct_tofu_global["host_key"]["known_hosts_file"] = "C:/Users/fixture/.ssh/known_hosts"
    expect_error(module, direct_tofu_global, "known_hosts_file_must_not_be_user_global")

    windows_session_tofu = fallback_payload()
    windows_session_tofu["host_key"]["receipt_path"] = "C:\\session\\tofu-receipt.json"
    windows_session_tofu["host_key"]["known_hosts_file"] = "C:\\session\\known_hosts"
    assert module.build_plan(windows_session_tofu)["host_key"]["mode"] == "session_tofu"

    forged_evidence = fallback_payload()
    forged_evidence["direct_openssh"]["evidence"]["tcp_connected"] = False
    expect_error(module, forged_evidence, "evidence_sha256_mismatch")

    unbound_ip = fallback_payload()
    unbound_ip["doh"]["selected_ip"] = "203.0.113.9"
    expect_error(module, unbound_ip, "selected_ip_not_in_hashed_response")

    insecure_doh = fallback_payload()
    insecure_doh["doh"]["resolver_url"] = "http://resolver.example/dns-query"
    expect_error(module, insecure_doh, "resolver_url_must_be_https")

    userinfo_doh = fallback_payload()
    userinfo_doh["doh"]["resolver_url"] = "https://user:pass@resolver.example/dns-query"
    expect_error(module, userinfo_doh, "resolver_url_must_be_https")

    query_secret_doh = fallback_payload()
    query_secret_doh["doh"]["resolver_url"] = "https://resolver.example/dns-query?token=fixture"
    expect_error(module, query_secret_doh, "resolver_url_must_be_https")

    invalid_fingerprint = base_payload()
    invalid_fingerprint["host_key"]["fingerprint"] = "SHA256:not-a-real-fingerprint"
    expect_error(module, invalid_fingerprint, "fingerprint_invalid")

    mismatched_receipt = fallback_payload()
    mismatched_receipt["host_key"]["receipt"]["port"] = 2222
    mismatched_receipt["host_key"]["receipt_sha256"] = canonical_sha(mismatched_receipt["host_key"]["receipt"])
    expect_error(module, mismatched_receipt, "session_tofu_receipt_binding_mismatch")

    invalid_timeout = base_payload()
    invalid_timeout["timeouts"]["banner_seconds"] = 0
    expect_error(module, invalid_timeout, "banner_seconds_out_of_range")

    secret_input = base_payload()
    secret_input["password"] = "fixture-do-not-store"
    expect_error(module, secret_input, "secret_field_forbidden")

    raw_key_shape = base_payload()
    raw_key_shape["target"]["identity_file"] = (
        "-----BEGIN OPENSSH " + "PRIVATE" + " KEY-----\nfixture-only"
    )
    expect_error(module, raw_key_shape, "identity_file_must_be_path_not_key_material")

    for secret_key in ("api-key", "APIKey", "APIToken", "privateKey", "credential", "access_token", "auth_token"):
        secret_variant = base_payload()
        secret_variant[secret_key] = "fixture-do-not-store"
        expect_error(module, secret_variant, "secret_field_forbidden")

    fake_ip_same_answer = fallback_payload("fake_ip")
    fake_ip_same_answer["direct_openssh"]["evidence"]["system_answer"] = "198.51.100.7"
    fake_ip_same_answer["direct_openssh"]["evidence_sha256"] = canonical_sha(
        fake_ip_same_answer["direct_openssh"]["evidence"]
    )
    fake_ip_same_answer["host_key"]["receipt"]["direct_evidence_sha256"] = (
        fake_ip_same_answer["direct_openssh"]["evidence_sha256"]
    )
    fake_ip_same_answer["host_key"]["receipt_sha256"] = canonical_sha(fake_ip_same_answer["host_key"]["receipt"])
    expect_error(module, fake_ip_same_answer, "fake_ip_evidence_invalid")

    fake_ip_unbound_doh = fallback_payload("fake_ip")
    fake_ip_unbound_doh["direct_openssh"]["evidence"]["doh_answer"] = "198.51.100.8"
    fake_ip_unbound_doh["direct_openssh"]["evidence_sha256"] = canonical_sha(
        fake_ip_unbound_doh["direct_openssh"]["evidence"]
    )
    fake_ip_unbound_doh["host_key"]["receipt"]["direct_evidence_sha256"] = (
        fake_ip_unbound_doh["direct_openssh"]["evidence_sha256"]
    )
    fake_ip_unbound_doh["host_key"]["receipt_sha256"] = canonical_sha(fake_ip_unbound_doh["host_key"]["receipt"])
    expect_error(module, fake_ip_unbound_doh, "fake_ip_doh_binding_mismatch")

    empty_direct_tofu = direct_tofu_payload()
    empty_direct_tofu["host_key"]["receipt"] = {}
    empty_direct_tofu["host_key"]["receipt_sha256"] = canonical_sha({})
    expect_error(module, empty_direct_tofu, "session_tofu_receipt_binding_mismatch")

    bool_schema = base_payload()
    bool_schema["schema_version"] = True
    expect_error(module, bool_schema, "schema_version_must_be_1")

    bool_exit = base_payload()
    bool_exit["direct_openssh"]["evidence"]["openssh_exit_code"] = False
    bool_exit["direct_openssh"]["evidence_sha256"] = canonical_sha(bool_exit["direct_openssh"]["evidence"])
    expect_error(module, bool_exit, "success_evidence_invalid")

    nested_secret = fallback_payload()
    nested_secret["doh"]["response"]["ssh_password"] = "fixture-do-not-store"
    nested_secret["doh"]["response_sha256"] = canonical_sha(nested_secret["doh"]["response"])
    nested_secret["host_key"]["receipt"]["doh_response_sha256"] = nested_secret["doh"]["response_sha256"]
    nested_secret["host_key"]["receipt_sha256"] = canonical_sha(nested_secret["host_key"]["receipt"])
    expect_error(module, nested_secret, "unknown_field:doh.response.ssh_password")

    polluted_answers = fallback_payload()
    polluted_answers["doh"]["response"]["answers"].append("fixture-secret")
    polluted_answers["doh"]["response_sha256"] = canonical_sha(polluted_answers["doh"]["response"])
    polluted_answers["host_key"]["receipt"]["doh_response_sha256"] = polluted_answers["doh"]["response_sha256"]
    polluted_answers["host_key"]["receipt_sha256"] = canonical_sha(polluted_answers["host_key"]["receipt"])
    expect_error(module, polluted_answers, "answers_must_be_ipv4_strings")

    with tempfile.TemporaryDirectory() as td:
        input_path = Path(td) / "input.json"
        output_path = Path(td) / "plan.json"
        input_path.write_text(json.dumps(fallback_payload()), encoding="utf-8")
        assert module.cli(["--input", str(input_path), "--output", str(output_path)]) == 0
        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written["transport"] == "paramiko_single_socket"

    assert NEGATIVE_CASES == 39, NEGATIVE_CASES
    print(f"WINDOWS_SSH_TRANSPORT_EVAL_OK direct=2 fallback=3 negatives={NEGATIVE_CASES} secret_variants=7 offline=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
