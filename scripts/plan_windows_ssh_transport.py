#!/usr/bin/env python3
"""Build a Windows high-port SSH transport plan from frozen evidence, offline only."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
FALLBACK_EVIDENCE = {"banner_timeout", "fake_ip", "tun_interference"}
DIRECT_REJECT = {"auth_failed", "host_key_mismatch", "connection_refused", "other_error"}
SECRET_FIELD_NAMES = {
    "password", "passwd", "token", "accesstoken", "refreshtoken", "bearer", "authorization",
    "secret", "clientsecret", "credential", "credentials", "privatekey", "apikey", "accesskey",
    "secretkey", "apitoken", "authtoken",
}


class PlanError(ValueError):
    """Fail-closed input-contract error."""


def exact_keys(mapping: dict[str, Any], allowed: set[str], scope: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise PlanError(f"unknown_field:{scope}.{unknown[0]}")


def require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{name}_must_be_object")
    return value


def require_text(mapping: dict[str, Any], key: str, scope: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{scope}.{key}_required")
    return value.strip()


def require_sha256(mapping: dict[str, Any], key: str, scope: str) -> str:
    value = require_text(mapping, key, scope)
    if not HEX64.fullmatch(value):
        raise PlanError(f"{scope}.{key}_must_be_sha256")
    return value.lower()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reject_secret_fields(value: Any, scope: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).casefold())
            if normalized in SECRET_FIELD_NAMES:
                raise PlanError(f"secret_field_forbidden:{scope}.{key}")
            reject_secret_fields(child, f"{scope}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secret_fields(child, f"{scope}[{index}]")


def validate_fingerprint(value: str) -> None:
    if not value.startswith("SHA256:"):
        raise PlanError("host_key.fingerprint_must_use_SHA256")
    encoded = value.removeprefix("SHA256:")
    try:
        decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
    except ValueError as exc:
        raise PlanError("host_key.fingerprint_invalid") from exc
    if len(decoded) != 32:
        raise PlanError("host_key.fingerprint_invalid")


def normalize_plan_path(value: str, field: str) -> str:
    """Pure-string path normalization; the planner never touches the filesystem."""
    if any(marker in value for marker in ("\x00", "\r", "\n")):
        raise PlanError(f"host_key.{field}_must_not_contain_control_characters")
    normalized = value.replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized.rstrip("/")


def validate_session_scoped_known_hosts(known_hosts_file: str, receipt_path: str) -> None:
    """session_tofu records a first-contact key, so it must never write a user-global known_hosts."""
    known_hosts = normalize_plan_path(known_hosts_file, "known_hosts_file")
    receipt = normalize_plan_path(receipt_path, "receipt_path")
    parts = known_hosts.split("/")
    lowered = known_hosts.casefold()
    if (
        ".." in parts
        or (len(parts) >= 2 and parts[-2].casefold() == ".ssh")
        or any(
            marker in lowered
            for marker in ("~/", "%userprofile%", "%homepath%", "$home", "${home}", "$env:userprofile")
        )
    ):
        raise PlanError("host_key.known_hosts_file_must_not_be_user_global")
    known_dir, _, known_name = known_hosts.rpartition("/")
    if not known_dir or not known_name or known_dir != receipt.rpartition("/")[0]:
        raise PlanError("host_key.known_hosts_file_must_be_session_scoped")


def validate_timeouts(payload: dict[str, Any]) -> dict[str, int]:
    timeouts = require_dict(payload.get("timeouts"), "timeouts")
    exact_keys(timeouts, {"connect_seconds", "banner_seconds"}, "timeouts")
    result: dict[str, int] = {}
    for key in ("connect_seconds", "banner_seconds"):
        value = timeouts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 120:
            raise PlanError(f"timeouts.{key}_out_of_range")
        result[key] = value
    return result


def validate_direct_evidence(direct: dict[str, Any], status: str) -> tuple[dict[str, Any], str]:
    exact_keys(direct, {"status", "evidence", "evidence_sha256"}, "direct_openssh")
    evidence = require_dict(direct.get("evidence"), "direct_openssh.evidence")
    evidence_keys = {
        "success": {"classification", "openssh_exit_code", "host_key_verified"},
        "banner_timeout": {"classification", "tcp_connected", "ssh_banner_received"},
        "fake_ip": {
            "classification", "system_answer", "doh_answer", "system_answer_is_fake_ip", "answers_differ",
        },
        "tun_interference": {"classification", "tun_interface_observed", "route_snapshot_sha256"},
    }.get(status, {"classification"})
    exact_keys(evidence, evidence_keys, "direct_openssh.evidence")
    if evidence.get("classification") != status:
        raise PlanError("direct_openssh.evidence_classification_mismatch")
    declared_sha = require_sha256(direct, "evidence_sha256", "direct_openssh")
    computed_sha = canonical_sha256(evidence)
    if declared_sha != computed_sha:
        raise PlanError("direct_openssh.evidence_sha256_mismatch")
    if status == "success":
        exit_code = evidence.get("openssh_exit_code")
        if (
            not isinstance(exit_code, int)
            or isinstance(exit_code, bool)
            or exit_code != 0
            or evidence.get("host_key_verified") is not True
        ):
            raise PlanError("direct_openssh.success_evidence_invalid")
    elif status == "banner_timeout":
        if evidence.get("tcp_connected") is not True or evidence.get("ssh_banner_received") is not False:
            raise PlanError("direct_openssh.banner_timeout_evidence_invalid")
    elif status == "fake_ip":
        try:
            system_answer = ipaddress.ip_address(str(evidence.get("system_answer")))
            doh_answer = ipaddress.ip_address(str(evidence.get("doh_answer")))
        except ValueError as exc:
            raise PlanError("direct_openssh.fake_ip_evidence_invalid") from exc
        if (
            evidence.get("system_answer_is_fake_ip") is not True
            or evidence.get("answers_differ") is not True
            or system_answer == doh_answer
        ):
            raise PlanError("direct_openssh.fake_ip_evidence_invalid")
    elif status == "tun_interference":
        if evidence.get("tun_interface_observed") is not True:
            raise PlanError("direct_openssh.tun_evidence_invalid")
        require_sha256(evidence, "route_snapshot_sha256", "direct_openssh.evidence")
    return evidence, computed_sha


def validate_target(payload: dict[str, Any]) -> dict[str, Any]:
    target = require_dict(payload.get("target"), "target")
    exact_keys(target, {"hostname", "port", "user", "identity_file"}, "target")
    hostname = require_text(target, "hostname", "target")
    user = require_text(target, "user", "target")
    identity_file = require_text(target, "identity_file", "target")
    if (
        len(identity_file) > 1024
        or any(marker in identity_file for marker in ("\x00", "\r", "\n", "-----BEGIN", "OPENSSH PRIVATE KEY"))
    ):
        raise PlanError("target.identity_file_must_be_path_not_key_material")
    port = target.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise PlanError("target.port_out_of_range")
    return {"hostname": hostname, "port": port, "user": user, "identity_file": identity_file}


def validate_host_key(payload: dict[str, Any]) -> dict[str, Any]:
    host_key = require_dict(payload.get("host_key"), "host_key")
    mode = require_text(host_key, "mode", "host_key")
    fingerprint = require_text(host_key, "fingerprint", "host_key")
    validate_fingerprint(fingerprint)
    result: dict[str, Any] = {"mode": mode, "fingerprint": fingerprint, "strict": True}
    if mode == "pinned":
        exact_keys(host_key, {"mode", "fingerprint", "known_hosts_file"}, "host_key")
        result["known_hosts_file"] = require_text(host_key, "known_hosts_file", "host_key")
    elif mode == "session_tofu":
        exact_keys(
            host_key,
            {"mode", "fingerprint", "receipt_path", "known_hosts_file", "receipt", "receipt_sha256"},
            "host_key",
        )
        result["receipt_path"] = require_text(host_key, "receipt_path", "host_key")
        result["known_hosts_file"] = require_text(host_key, "known_hosts_file", "host_key")
        validate_session_scoped_known_hosts(result["known_hosts_file"], result["receipt_path"])
        result["receipt"] = require_dict(host_key.get("receipt"), "host_key.receipt")
        result["receipt_sha256"] = require_sha256(host_key, "receipt_sha256", "host_key")
        if result["receipt_sha256"] != canonical_sha256(result["receipt"]):
            raise PlanError("host_key.receipt_sha256_mismatch")
    else:
        raise PlanError("host_key.mode_must_be_pinned_or_session_tofu")
    return result


def validate_session_tofu_receipt(
    host_key: dict[str, Any],
    target: dict[str, Any],
    session_id: str,
    evidence_sha256: str,
    *,
    selected_ip: str | None = None,
    doh_response_sha256: str | None = None,
) -> None:
    if host_key["mode"] != "session_tofu":
        return
    receipt = host_key["receipt"]
    expected_receipt: dict[str, Any] = {
        "session_id": session_id,
        "logical_hostname": target["hostname"],
        "port": target["port"],
        "key_type": receipt.get("key_type"),
        "fingerprint": host_key["fingerprint"],
        "observed_at": receipt.get("observed_at"),
        "direct_evidence_sha256": evidence_sha256,
        "first_contact_mitm_unavailable": True,
    }
    if selected_ip is not None:
        expected_receipt["selected_ip"] = selected_ip
        expected_receipt["doh_response_sha256"] = doh_response_sha256
    if (
        not isinstance(receipt.get("key_type"), str)
        or not receipt.get("key_type")
        or not isinstance(receipt.get("observed_at"), str)
        or not receipt.get("observed_at")
        or receipt != expected_receipt
    ):
        raise PlanError("host_key.session_tofu_receipt_binding_mismatch")


def build_plan(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PlanError("payload_must_be_object")
    if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
        raise PlanError("schema_version_must_be_1")
    reject_secret_fields(payload)
    exact_keys(
        payload,
        {"schema_version", "session_id", "target", "timeouts", "direct_openssh", "host_key", "doh", "windows"},
        "payload",
    )
    session_id = require_text(payload, "session_id", "payload")
    target = validate_target(payload)
    timeouts = validate_timeouts(payload)
    host_key = validate_host_key(payload)
    direct = require_dict(payload.get("direct_openssh"), "direct_openssh")
    status = require_text(direct, "status", "direct_openssh")
    direct_evidence, evidence_sha256 = validate_direct_evidence(direct, status)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    common = {
        "schema_version": 1,
        "offline_only": True,
        "session_id": session_id,
        "logical_hostname": target["hostname"],
        "port": target["port"],
        "user": target["user"],
        "identity_file": target["identity_file"],
        "direct_openssh_status": status,
        "direct_evidence_sha256": evidence_sha256,
        "timeouts": timeouts,
        "decision_input_sha256": hashlib.sha256(canonical).hexdigest(),
        "host_key": host_key,
        "system_mutations": [],
    }
    if status == "success":
        if "doh" in payload or "windows" in payload:
            raise PlanError("unexpected_fallback_fields_for_direct_success")
        validate_session_tofu_receipt(host_key, target, session_id, evidence_sha256)
        return {
            **common,
            "transport": "openssh_direct",
            "connect_host": target["hostname"],
            "openssh": {
                "strict_host_key_checking": "yes",
                "user_known_hosts_file": host_key.get("known_hosts_file") or host_key.get("receipt_path"),
            },
        }
    if status in DIRECT_REJECT or status not in FALLBACK_EVIDENCE:
        raise PlanError(f"fallback_not_authorized:{status}")

    doh = require_dict(payload.get("doh"), "doh")
    exact_keys(
        doh,
        {"resolver_url", "hostname", "observed_at", "response", "response_sha256", "selected_ip"},
        "doh",
    )
    resolver_url = require_text(doh, "resolver_url", "doh")
    try:
        parsed_url = urlsplit(resolver_url)
        parsed_port = parsed_url.port
    except ValueError as exc:
        raise PlanError("doh.resolver_url_invalid") from exc
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
        or parsed_url.path not in {"", "/", "/dns-query", "/resolve"}
        or (parsed_port is not None and not 1 <= parsed_port <= 65535)
    ):
        raise PlanError("doh.resolver_url_must_be_https")
    doh_hostname = require_text(doh, "hostname", "doh")
    if doh_hostname != target["hostname"]:
        raise PlanError("doh.hostname_mismatch")
    observed_at = require_text(doh, "observed_at", "doh")
    response = require_dict(doh.get("response"), "doh.response")
    exact_keys(response, {"answers"}, "doh.response")
    response_sha256 = require_sha256(doh, "response_sha256", "doh")
    if response_sha256 != canonical_sha256(response):
        raise PlanError("doh.response_sha256_mismatch")
    selected_ip = require_text(doh, "selected_ip", "doh")
    try:
        parsed = ipaddress.ip_address(selected_ip)
    except ValueError as exc:
        raise PlanError("doh.selected_ip_invalid") from exc
    if parsed.version != 4:
        raise PlanError("doh.selected_ip_must_be_ipv4_for_IP_UNICAST_IF")
    answers = response.get("answers")
    if not isinstance(answers, list) or selected_ip not in answers:
        raise PlanError("doh.selected_ip_not_in_hashed_response")
    try:
        normalized_answers = [str(ipaddress.ip_address(answer)) for answer in answers]
    except (TypeError, ValueError) as exc:
        raise PlanError("doh.answers_must_be_ipv4_strings") from exc
    if (
        not answers
        or any(not isinstance(answer, str) for answer in answers)
        or any(ipaddress.ip_address(answer).version != 4 for answer in answers)
        or normalized_answers != answers
        or len(answers) != len(set(answers))
    ):
        raise PlanError("doh.answers_must_be_unique_canonical_ipv4")
    if status == "fake_ip" and direct_evidence.get("doh_answer") != selected_ip:
        raise PlanError("direct_openssh.fake_ip_doh_binding_mismatch")

    windows = require_dict(payload.get("windows"), "windows")
    exact_keys(windows, {"interface_index"}, "windows")
    interface_index = windows.get("interface_index")
    if (
        not isinstance(interface_index, int)
        or isinstance(interface_index, bool)
        or not 1 <= interface_index <= 0xFFFFFFFF
    ):
        raise PlanError("windows.interface_index_must_be_positive_integer")

    validate_session_tofu_receipt(
        host_key,
        target,
        session_id,
        evidence_sha256,
        selected_ip=selected_ip,
        doh_response_sha256=response_sha256,
    )

    return {
        **common,
        "transport": "paramiko_single_socket",
        "connect_host": selected_ip,
        "doh": {
            "resolver_url": resolver_url,
            "hostname": doh_hostname,
            "observed_at": observed_at,
            "response_sha256": response_sha256,
            "response": response,
            "selected_ip": selected_ip,
        },
        "windows_socket": {
            "family": "AF_INET",
            "option": "IP_UNICAST_IF",
            "interface_index": interface_index,
            "reuse_contract": "single connected socket handed to Paramiko Transport",
        },
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Frozen evidence JSON; no secrets")
    parser.add_argument("--output", required=True, type=Path, help="Destination for the offline plan JSON")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        plan = build_plan(payload)
    except (OSError, json.JSONDecodeError, PlanError) as exc:
        print(json.dumps({"status": "WINDOWS_SSH_PLAN_INVALID", "problem": str(exc)}, ensure_ascii=False))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "WINDOWS_SSH_PLAN_VALID", "transport": plan["transport"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
