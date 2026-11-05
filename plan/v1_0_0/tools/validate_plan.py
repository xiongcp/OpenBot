#!/usr/bin/env python3
"""Validate the OpenBot planning and execution package, not the OpenBot product.

Run from any directory:
    python3 /path/to/package/tools/validate_plan.py [--mode {plan,execution,rc}] [--no-write]

Modes:
  - plan (default): Static handover check; requires all tasks PLANNED/NOT_RUN and all cases/gates NOT_RUN.
  - execution: In-progress execution check; allows tasks in PLANNED/IN_PROGRESS/DONE/VERIFIED/BLOCKED
    and test cases in NOT_RUN/PASS/FAIL/BLOCKED/SKIPPED, verifying SHA format when completed.
  - rc: Release candidate check; requires all P0/P1 v1.0.0 scope tasks and mandatory gates to be PASS/VERIFIED.

Exit codes: 0 = structural checks passed, 1 = failed, 2 = optional checks skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import ipaddress
import json
import platform
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


TASK_FIELDS = {
    "id", "title", "priority", "phase", "lane", "legacy_ids", "depends_on",
    "deliverables", "steps", "acceptance", "negative_tests", "current_evidence",
    "size", "status", "release_requirement", "implementation_status",
    "execution_result", "introduced_by_sha", "verified_on_sha", "commit_sha",
    "push_receipt", "required_test_ids", "gate_ids",
}
CASE_FIELDS = {
    "id", "title", "gate", "priority", "environment", "preconditions", "steps",
    "expected", "evidence", "failure_diagnosis", "fix_direction", "regression",
    "requires_real_environment", "status", "result", "design_origin",
    "command_binding_status", "related_tasks", "related_v1_tasks",
}
CASE_COUNTS = {"QA": 8, "CORE": 44, "MAC": 22, "INT": 16, "GIT": 6, "EVAL": 4, "V1": 40}
REQUIRED_SOURCES = {
    *(f"R{i:02}" for i in range(1, 24)),
    *(f"W{i:02}" for i in range(1, 12)),
}
NON_GATE_P0_ALLOW_P1_DEPS = {"V1-037", "V1-038", "V1-039"}

REF_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([RW])(\d{1,3})(?![A-Za-z0-9_])")
REF_RANGE = re.compile(
    r"(?<![A-Za-z0-9_])([RW])(\d{1,3})\s*"
    r"(?:-|\u2013|\u2014|~|\uff5e|\u81f3|\.\.|\u2026)\s*"
    r"([RW])?(\d{1,3})(?![A-Za-z0-9_])"
)
LOCAL_REF_TOKEN = re.compile(r"(?<![A-Za-z0-9_])([ARSW])(\d{2,3})(?![A-Za-z0-9_])")
LOCAL_REF_RANGE = re.compile(
    r"(?<![A-Za-z0-9_])([ARSW])(\d{2,3})\s*"
    r"(?:-|\u2013|\u2014|~|\uff5e|\u81f3|\.\.|\u2026)\s*"
    r"([ARSW])?(\d{2,3})(?![A-Za-z0-9_])"
)
LOCAL_DEFINITION = re.compile(
    r"^\s*(?:(?:[-*]|\#{1,6})\s+|\|\s*)?"
    r"(?:\*\*|\[)?([ARSW]\d{2,3})(?:\*\*|\])?"
    r"(?=\s|[:\uff1a|])"
)
EXPLICIT_GLOBAL_REF = re.compile(
    r"(?:sources?|global|\u4e3b\u7d22\u5f15|\u5168\u5c40\u6765\u6e90)"
    r"\s*[:\uff1a]?\s*([RW]\d{2,3})", re.IGNORECASE
)
HTTP_URL = re.compile(r"https?://[^\s<>\])\uff1b;|]+")
SHA40 = re.compile(r"^[a-f0-9]{40}$")


class ValidationFailure(Exception):
    pass


class CheckSkipped(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(nonempty_string(item) for item in value)
    )


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


def expand_source_refs(text: str, *, local: bool = False) -> tuple[set[str], int]:
    """Expand both R02-R05 and R02-05, plus Chinese/en-dash range spellings."""
    token_pattern = LOCAL_REF_TOKEN if local else REF_TOKEN
    range_pattern = LOCAL_REF_RANGE if local else REF_RANGE
    found = {f"{prefix}{int(number):02}" for prefix, number in token_pattern.findall(text)}
    ranges = 0
    for match in range_pattern.finditer(text):
        prefix, first, end_prefix, last = match.groups()
        require(end_prefix in (None, prefix), f"Cross-family source range: {match.group(0)}")
        start, end = int(first), int(last)
        require(0 < start <= end <= 999, f"Invalid source range: {match.group(0)}")
        found.update(f"{prefix}{number:02}" for number in range(start, end + 1))
        ranges += 1
    return found, ranges


def limited_http_uri(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    if not value or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return False
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port is not None and not 0 <= parsed.port <= 65535:
            return False
        host = parsed.hostname
        if ":" in host:
            if "%" in host:
                return False
            ipaddress.IPv6Address(host)
        else:
            host = host.removesuffix(".")
            if len(host) > 253 or not host:
                return False
            labels = host.split(".")
            if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                   for label in labels):
                return False
            if len(labels) == 4 and all(label.isdigit() for label in labels):
                ipaddress.IPv4Address(host)
        path_chars = r"[A-Za-z0-9._~!$&'()*+,;=:@%/\-]*"
        query_chars = r"[A-Za-z0-9._~!$&'()*+,;=:@%/?\-]*"
        return (
            re.fullmatch(path_chars, parsed.path) is not None
            and re.fullmatch(query_chars, parsed.query) is not None
            and re.fullmatch(query_chars, parsed.fragment) is not None
        )
    except ValueError:
        return False


def limited_rfc3339_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
        r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)", value
    ) is None:
        return False
    try:
        normalized = value.replace("t", "T")
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized).tzinfo is not None
    except ValueError:
        return False


class PlanValidator:
    def __init__(self, root: Path, *, mode: str = "plan"):
        self.root = root.resolve()
        self.mode = mode
        self.docs: dict[str, Any] = {}
        self.inputs: dict[str, dict[str, Any]] = {}
        self.checks: list[dict[str, Any]] = []
        self.optional_versions: dict[str, str | None] = {}

    def read_text(self, path: Path) -> str:
        require(path.resolve().is_relative_to(self.root), f"Input escapes package root: {path.name}")
        raw = path.read_bytes()
        relative = path.relative_to(self.root).as_posix()
        self.inputs[relative] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
        return raw.decode("utf-8")

    def document(self, relative: str) -> Any:
        require(relative in self.docs, f"JSON input unavailable or invalid: {relative}")
        return self.docs[relative]

    def run_check(self, name: str, action: Any) -> None:
        try:
            details = action()
        except CheckSkipped as exc:
            self.checks.append({"id": name, "status": "SKIPPED", "reason": str(exc)})
        except Exception as exc:
            self.checks.append({
                "id": name, "status": "FAIL",
                "error": f"{type(exc).__name__}: {exc}",
            })
        else:
            self.checks.append({"id": name, "status": "PASS", "details": details})

    def repo_collision_guard(self) -> dict[str, Any]:
        require(
            not (self.root / "validation" / "verify_design.py").exists(),
            "Package was unpacked directly over the OpenBot repository root! "
            "Mount it under plan/v1_0_0/ or outside the repository root to avoid overwriting OB-001..096.",
        )
        return {
            "isolated_from_repo_root": True,
            "recommended_mount_path": self.document("tasks/backlog.json").get("recommended_mount_path"),
        }

    def json_syntax(self) -> dict[str, Any]:
        paths = sorted(
            path for path in self.root.rglob("*.json")
            if path.relative_to(self.root).as_posix() != "evidence/package_validation.json"
        )
        errors = []
        for path in paths:
            relative = path.relative_to(self.root).as_posix()
            try:
                self.docs[relative] = json.loads(
                    self.read_text(path),
                    object_pairs_hook=no_duplicate_keys,
                    parse_constant=reject_json_constant,
                )
            except Exception as exc:
                errors.append(f"{relative}: {type(exc).__name__}: {exc}")
        require(bool(paths), "No package JSON files found")
        require(not errors, "; ".join(errors))
        return {
            "files_checked": len(paths),
            "duplicate_keys_and_nonfinite_numbers_rejected": True,
            "generated_report_excluded": True,
        }

    def yaml_syntax(self) -> dict[str, Any]:
        paths = sorted(
            path for path in self.root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
        )
        if not paths:
            return {"files_checked": 0, "note": "No YAML files present"}
        try:
            yaml = importlib.import_module("yaml")
        except ImportError:
            self.optional_versions["PyYAML"] = None
            raise CheckSkipped(f"PyYAML unavailable; YAML syntax not checked ({len(paths)} files)")
        self.optional_versions["PyYAML"] = importlib.metadata.version("PyYAML")
        errors = []
        for path in paths:
            try:
                list(yaml.safe_load_all(self.read_text(path)))
            except Exception as exc:
                errors.append(f"{path.relative_to(self.root)}: {type(exc).__name__}: {exc}")
        require(not errors, "; ".join(errors))
        return {"files_checked": len(paths), "loader": "safe_load_all", "schema_validation": False}

    def task_records(self) -> list[dict[str, Any]]:
        doc = self.document("tasks/backlog.json")
        require(isinstance(doc, dict) and isinstance(doc.get("tasks"), list), "Invalid backlog envelope")
        return doc["tasks"]

    def task_fields(self) -> dict[str, Any]:
        tasks = self.task_records()
        require(len(tasks) == 84, f"Expected 84 tasks; found {len(tasks)}")
        ids = []
        all_ob_covered: set[str] = set()
        for task in tasks:
            require(isinstance(task, dict), "Task must be an object")
            missing = TASK_FIELDS - task.keys()
            require(not missing, f"{task.get('id')}: missing fields {sorted(missing)}")
            tid = task["id"]
            require(isinstance(tid, str), "Task ID must be a string")
            ids.append(tid)
            for key in ("title", "lane", "current_evidence", "implementation_status"):
                require(nonempty_string(task[key]), f"{tid}: {key} must be nonempty text")
            require(task["priority"] in {"P0", "P1", "P2"}, f"{tid}: invalid priority")
            require(task["phase"] in {"alpha", "beta", "rc", "post-v1"}, f"{tid}: invalid phase")
            require(task["size"] in {"S", "M", "L"}, f"{tid}: invalid size")
            if self.mode == "plan":
                require(task["status"] == "PLANNED", f"{tid}: planning package must remain PLANNED")
                require(task["execution_result"] == "NOT_RUN", f"{tid}: must not claim product execution")
                for key in ("introduced_by_sha", "verified_on_sha", "commit_sha", "push_receipt"):
                    require(task[key] is None, f"{tid}: plan must not contain invented {key}")
            elif self.mode == "execution":
                require(
                    task["status"] in {"PLANNED", "IN_PROGRESS", "VERIFIED", "DONE", "BLOCKED"},
                    f"{tid}: invalid execution status {task['status']}",
                )
                require(
                    task["execution_result"] in {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "PARTIAL"},
                    f"{tid}: invalid execution_result {task['execution_result']}",
                )
                if task["status"] in {"VERIFIED", "DONE"}:
                    require(
                        isinstance(task["verified_on_sha"], str) and SHA40.fullmatch(task["verified_on_sha"]) is not None,
                        f"{tid}: VERIFIED/DONE task requires 40-hex verified_on_sha",
                    )
            elif self.mode == "rc":
                if task["release_requirement"] == "REQUIRED_FOR_PROPOSED_SCOPE":
                    require(
                        task["status"] in {"VERIFIED", "DONE"} and task["execution_result"] == "PASS",
                        f"{tid}: RC mode requires all scoped tasks VERIFIED/DONE and PASS",
                    )
            for key in ("deliverables", "steps", "acceptance", "negative_tests", "legacy_ids", "required_test_ids", "gate_ids"):
                require(string_list(task[key]), f"{tid}: {key} must be a nonempty text list")
            require(string_list(task["depends_on"], allow_empty=True), f"{tid}: invalid dependencies")
            for key, minimum, maximum in (("steps", 3, 5), ("acceptance", 2, 4), ("negative_tests", 1, 3)):
                require(minimum <= len(task[key]) <= maximum, f"{tid}: {key} count outside {minimum}..{maximum}")
            legacy = task["legacy_ids"]
            require(len(legacy) == len(set(legacy)), f"{tid}: duplicate legacy IDs")
            require(all(re.fullmatch(r"OB-\d{3}", x) and 1 <= int(x[3:]) <= 96 for x in legacy),
                    f"{tid}: unknown original OB ID")
            all_ob_covered.update(legacy)
        expected = {f"V1-{i:03}" for i in range(1, 85)}
        require(len(set(ids)) == len(ids), "Duplicate task IDs")
        require(set(ids) == expected, f"Task ID mismatch: {sorted(set(ids) ^ expected)}")
        expected_ob = {f"OB-{i:03}" for i in range(1, 97)}
        require(
            all_ob_covered == expected_ob,
            f"Legacy OB-001..096 coverage incomplete; missing: {sorted(expected_ob - all_ob_covered)}",
        )
        require(SHA40.fullmatch(self.document("tasks/backlog.json").get("review_sha", "")) is not None,
                "Backlog review_sha must be a full SHA")
        return {
            "tasks": len(tasks), "required_fields": len(TASK_FIELDS),
            "legacy_ob_tasks_covered": len(all_ob_covered),
            "priority_counts": dict(Counter(t["priority"] for t in tasks)),
            "phase_counts": dict(Counter(t["phase"] for t in tasks)),
            "validation_mode": self.mode,
        }

    def task_graph(self) -> dict[str, Any]:
        tasks = self.task_records()
        by_id = {t["id"]: t for t in tasks}
        require(len(by_id) == len(tasks), "Duplicate task IDs")
        phase_rank = {"alpha": 0, "beta": 1, "rc": 2, "post-v1": 3}
        pri_rank = {"P0": 0, "P1": 1, "P2": 2}
        edges = 0
        for tid, task in by_id.items():
            deps = task["depends_on"]
            require(len(deps) == len(set(deps)), f"{tid}: repeated dependency")
            for dependency in deps:
                require(dependency in by_id, f"{tid}: unknown dependency {dependency}")
                require(dependency != tid, f"{tid}: self dependency")
                dt = by_id[dependency]
                require(
                    phase_rank[dt["phase"]] <= phase_rank[task["phase"]],
                    f"Phase inversion: {tid} ({task['phase']}) depends on {dependency} ({dt['phase']})",
                )
                if tid not in NON_GATE_P0_ALLOW_P1_DEPS:
                    require(
                        pri_rank[dt["priority"]] <= pri_rank[task["priority"]],
                        f"Priority inversion on implementation task: {tid} ({task['priority']}) depends on {dependency} ({dt['priority']})",
                    )
                edges += 1
        # Verify V1-031 and V1-033 do not hard-depend on live external tenant V1-027 or local model V1-021
        for pkg_tid in ("V1-031", "V1-033"):
            require(
                not ({"V1-021", "V1-027"} & set(by_id[pkg_tid]["depends_on"])),
                f"{pkg_tid} must not be blocked by external tenant/model tasks V1-021 or V1-027",
            )
        active: list[str] = []
        complete: set[str] = set()

        def visit(tid: str) -> None:
            require(tid not in active, f"Dependency cycle: {' -> '.join(active + [tid])}")
            if tid in complete:
                return
            active.append(tid)
            for dependency in by_id[tid]["depends_on"]:
                visit(dependency)
            active.pop()
            complete.add(tid)

        for tid in by_id:
            visit(tid)
        return {
            "nodes": len(by_id),
            "edges": edges,
            "acyclic": True,
            "phase_monotonic": True,
            "non_gate_p0_priority_monotonic": True,
            "packaging_decoupled_from_live_tenant": True,
        }

    def release_closure(self) -> dict[str, Any]:
        by_id = {t["id"]: t for t in self.task_records()}
        seen: set[str] = set()
        todo = list(by_id["V1-039"]["depends_on"])
        while todo:
            tid = todo.pop()
            require(tid in by_id, f"Unknown dependency in RC closure: {tid}")
            if tid in seen:
                continue
            seen.add(tid)
            todo.extend(by_id[tid]["depends_on"])
        required = ({f"V1-{i:03}" for i in range(1, 56)} | {f"V1-{i:03}" for i in range(61, 85)}) - {"V1-039"}
        require(seen == required,
                f"RC closure missing={sorted(required - seen)}, unexpected={sorted(seen - required)}")
        require("V1-045" in by_id["V1-035"]["depends_on"], "V1-035 must directly depend on V1-045")
        for number in range(1, 85):
            tid = f"V1-{number:03}"
            expected = (
                "CONDITIONAL_WITH_APPROVED_MANUAL_UPDATE" if number == 34
                else "POST_V1" if 56 <= number <= 60
                else "REQUIRED_FOR_PROPOSED_SCOPE"
            )
            require(by_id[tid]["release_requirement"] == expected, f"{tid}: inconsistent release requirement")
        updater_text = json.dumps(by_id["V1-034"], ensure_ascii=False)
        require("ADR" in updater_text and "手工" in updater_text and "替代" in updater_text,
                "V1-034 must document an explicit manual-update alternative")
        return {
            "rc_task": "V1-039", "required_prerequisites": 78,
            "actual_prerequisites": len(seen), "missing": [],
            "license_dependency": "V1-035 -> V1-045",
            "manual_update_alternative": "Explicit scope decision; not automatic PASS",
        }

    def case_records(self) -> list[dict[str, Any]]:
        doc = self.document("testing/test_cases.json")
        require(isinstance(doc, dict) and isinstance(doc.get("cases"), list), "Invalid cases envelope")
        return doc["cases"]

    def cases(self) -> dict[str, Any]:
        doc = self.document("testing/test_cases.json")
        cases = self.case_records()
        expected_ids = {f"TC-{group}-{i:03}" for group, count in CASE_COUNTS.items() for i in range(1, count + 1)}
        require(len(cases) == 140, f"Expected 140 cases; found {len(cases)}")
        ids = []
        task_ids = {t["id"] for t in self.task_records()}
        for case in cases:
            require(isinstance(case, dict), "Case must be an object")
            require(not CASE_FIELDS - case.keys(), f"{case.get('id')}: missing case fields {sorted(CASE_FIELDS - case.keys())}")
            cid = case["id"]
            require(isinstance(cid, str), "Case ID must be text")
            ids.append(cid)
            for key in ("title", "gate", "environment", "design_origin", "command_binding_status"):
                require(nonempty_string(case[key]), f"{cid}: missing {key}")
            for key in ("preconditions", "steps", "expected", "evidence", "failure_diagnosis", "fix_direction", "regression"):
                require(string_list(case[key]), f"{cid}: invalid {key}")
            require(
                case["failure_diagnosis"] != case["fix_direction"],
                f"{cid}: failure_diagnosis and fix_direction must not be identical copy-pasted text",
            )
            require(case["priority"] in {"P0", "P1", "P2"}, f"{cid}: invalid priority")
            require(type(case["requires_real_environment"]) is bool, f"{cid}: environment flag must be boolean")
            if self.mode == "plan":
                require(case["status"] == "NOT_RUN" and case["result"] is None,
                        f"{cid}: this plan package must not contain product results")
            else:
                require(
                    case["status"] in {"NOT_RUN", "PASS", "FAIL", "BLOCKED", "SKIPPED", "NOT_APPLICABLE"},
                    f"{cid}: invalid case status {case['status']}",
                )
            require(string_list(case.get("related_tasks")), f"{cid}: missing related_tasks (OB-*)")
            require(string_list(case.get("related_v1_tasks")), f"{cid}: missing related_v1_tasks (V1-*)")
            for related in case["related_v1_tasks"]:
                require(related in task_ids, f"{cid}: unknown V1 mapping {related}")
            for related_ob in case["related_tasks"]:
                require(re.fullmatch(r"OB-\d{3}", related_ob) is not None and 1 <= int(related_ob[3:]) <= 96,
                        f"{cid}: unknown original OB mapping {related_ob}")
        require(len(ids) == len(set(ids)), "Duplicate test case IDs")
        require(set(ids) == expected_ids, f"Test ID mismatch: {sorted(set(ids) ^ expected_ids)}")
        require(doc.get("counts") == CASE_COUNTS, "Case envelope counts do not match 100 inherited + 40 new")
        for key in ("review_snapshot_sha", "inherited_design_sha"):
            require(isinstance(doc.get(key), str) and SHA40.fullmatch(doc[key]) is not None, f"Invalid {key}")
        require(nonempty_string(doc.get("notice")), "Case envelope must declare design/execution boundary")
        return {
            "cases": len(cases), "group_counts": CASE_COUNTS,
            "bidirectional_ob_and_v1_links": True,
            "distinct_diagnosis_and_fix_direction": True,
            "inherited_design_sha": doc["inherited_design_sha"],
            "review_snapshot_sha": doc["review_snapshot_sha"],
        }

    def gates(self) -> dict[str, Any]:
        doc = self.document("testing/gates.json")
        gates = doc.get("gates")
        require(isinstance(gates, list), "gates must be a list")
        ids = [gate["id"] for gate in gates]
        require(len(ids) == 8 and set(ids) == {f"G{i}" for i in range(1, 9)}, "Expected unique G1..G8")
        case_ids = {case["id"] for case in self.case_records()}
        covered: set[str] = set()
        total = 0
        for gate in gates:
            if self.mode == "plan":
                require(gate.get("status") == "NOT_RUN", f"{gate['id']}: gate must remain NOT_RUN")
            elif self.mode == "rc":
                require(gate.get("status") == "PASS", f"{gate['id']}: RC mode requires all 8 gates PASS")
            mapped = gate.get("test_ids")
            require(string_list(mapped), f"{gate['id']}: missing test mappings")
            require(len(mapped) == len(set(mapped)), f"{gate['id']}: duplicate case mapping")
            require(not set(mapped) - case_ids, f"{gate['id']}: unknown case IDs {sorted(set(mapped) - case_ids)}")
            covered.update(mapped)
            total += len(mapped)
        require(covered == case_ids, f"Unmapped cases: {sorted(case_ids - covered)}")
        conditional = doc.get("conditional_cases")
        require(isinstance(conditional, dict), "Missing conditional case decisions")
        require(not conditional.keys() - case_ids, "Conditional decision references unknown case")
        require(nonempty_string(conditional.get("TC-MAC-002")), "Intel/Rosetta applicability must be explicit")
        manual = conditional.get("TC-V1-015", "")
        require(nonempty_string(manual) and "manual" in manual.lower() and "TC-V1-014" in manual,
                "Updater alternative must retain explicit manual decision and TC-V1-014")
        return {
            "gates": len(gates),
            "mapping_entries": total,
            "unique_cases_covered": len(covered),
            "conditional_cases_documented": len(conditional),
        }

    def sources(self) -> dict[str, Any]:
        sources = self.document("evidence/sources.json")
        require(isinstance(sources, dict), "Source index must be an object")
        require(not REQUIRED_SOURCES - sources.keys(), f"Missing sources: {sorted(REQUIRED_SOURCES - sources.keys())}")
        for key, item in sources.items():
            require(re.fullmatch(r"[RW]\d{2,3}", key) is not None, f"Invalid source ID {key}")
            require(isinstance(item, dict) and nonempty_string(item.get("title")), f"{key}: missing title")
            require(string_list(item.get("urls")), f"{key}: missing source URLs")
            for url in item["urls"]:
                parsed = urlsplit(url)
                require(parsed.scheme == "https" and bool(parsed.netloc), f"{key}: invalid HTTPS URL {url}")
        for key in ("R22", "R23"):
            require(all(
                re.match(r"https://github\.com/xiongcp/OpenBot/blob/[a-f0-9]{40}/", url)
                for url in sources[key]["urls"]
            ), f"{key}: expected fixed-commit source links")
        return {
            "minimum_required": len(REQUIRED_SOURCES),
            "defined": len(sources),
            "additional_sources_allowed": sorted(sources.keys() - REQUIRED_SOURCES),
            "R22_R23_defined_with_fixed_commit_links": True,
            "network_reachability_checked": False,
        }

    def citations(self) -> dict[str, Any]:
        sources = self.document("evidence/sources.json")
        paths = sorted(self.root.rglob("*.md"))
        paths += sorted((self.root / "tasks").glob("*.json"))
        references: set[str] = set()
        ranges = occurrences = 0
        errors = []
        local_reports = []
        for path in paths:
            lines = self.read_text(path).splitlines()
            historical = path.parent == self.root / "evidence" and path.name.startswith("source_audit_")
            local_definitions: dict[str, int] = {}
            if historical:
                definition_starts = []
                for index, line in enumerate(lines):
                    match = LOCAL_DEFINITION.match(line)
                    if match:
                        sid = match.group(1)
                        if sid in local_definitions:
                            errors.append(f"{path.relative_to(self.root)}:{index + 1}: duplicate local definition {sid}")
                        local_definitions[sid] = index
                        definition_starts.append((index, sid))
                for offset, (index, sid) in enumerate(definition_starts):
                    end = definition_starts[offset + 1][0] if offset + 1 < len(definition_starts) else len(lines)
                    block = "\n".join(lines[index:end])
                    urls = HTTP_URL.findall(block)
                    if not urls or any(urlsplit(url).scheme != "https" or not urlsplit(url).netloc for url in urls):
                        errors.append(f"{path.relative_to(self.root)}:{index + 1}: {sid} has no valid HTTPS definition link")
                local_reports.append({
                    "file": path.relative_to(self.root).as_posix(),
                    "local_definitions": len(local_definitions),
                    "namespace_rule": "Local A/R/S/W families take precedence; explicit 'sources Rxx' uses the global index.",
                })
            local_families = {sid[0] for sid in local_definitions}
            for line_number, line in enumerate(lines, 1):
                found, expanded = expand_source_refs(line, local=historical)
                ranges += expanded
                if found:
                    occurrences += 1
                references.update(found)
                explicit_global = {sid.upper() for sid in EXPLICIT_GLOBAL_REF.findall(line)}
                for sid in sorted(found):
                    if historical and sid[0] in local_families and sid not in explicit_global:
                        if sid not in local_definitions:
                            errors.append(f"{path.relative_to(self.root)}:{line_number}: undefined local source {sid}")
                    elif sid not in sources:
                        errors.append(f"{path.relative_to(self.root)}:{line_number}: undefined global source {sid}")
        require(not errors, "; ".join(errors))
        return {
            "document_files_checked": len(paths),
            "lines_with_source_ids": occurrences,
            "unique_source_ids_referenced": len(references),
            "ranges_expanded": ranges, "unresolved_source_ids": [],
            "historical_report_namespaces": local_reports,
            "global_scope": "All other Markdown and tasks JSON resolve R/W references against evidence/sources.json.",
            "note": "Validates reference definitions and local HTTPS link syntax; does not prove source truth or URL availability.",
        }

    def prelaunch_manifest(self) -> dict[str, Any]:
        doc = self.document("website/releases.prelaunch.example.json")
        require(isinstance(doc, dict), "Prelaunch manifest must be an object")
        required = {
            "schema_version", "project", "stage", "stable_release",
            "beta_release", "source_repository", "notice",
        }
        require(doc.keys() == required, "Prelaunch manifest field mismatch")
        require(type(doc["schema_version"]) is int and doc["schema_version"] == 1, "Invalid manifest version")
        require(doc["project"] == "OpenBot" and doc["stage"] == "development", "Example must remain prelaunch")
        require(doc["stable_release"] is None and doc["beta_release"] is None,
                "Prelaunch example must not invent stable or beta binaries")
        require(doc["source_repository"] == "https://github.com/xiongcp/OpenBot", "Unexpected source repository")
        require(nonempty_string(doc["notice"]), "Prelaunch boundary notice is required")
        return {"stage": doc["stage"], "stable_release": None, "beta_release": None, "claims_published_binary": False}

    def website_schema(self) -> dict[str, Any]:
        schema = self.document("website/release_manifest.schema.json")
        require(isinstance(schema, dict), "Manifest schema must be an object")
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "Expected Draft 2020-12")
        formats: set[str] = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"$ref", "$dynamicRef"}:
                        require(isinstance(item, str) and item.startswith("#"),
                                "External schema reference forbidden in offline package validation")
                    if key == "format" and isinstance(item, str):
                        formats.add(item)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(schema)
        try:
            module = importlib.import_module("jsonschema")
        except ImportError:
            self.optional_versions["jsonschema"] = None
            raise CheckSkipped("jsonschema unavailable; full schema/format validation not performed")
        self.optional_versions["jsonschema"] = importlib.metadata.version("jsonschema")
        checker = module.FormatChecker()
        format_modes = {name: "jsonschema registered checker" for name in formats if name in checker.checkers}
        fallback_probes = {}
        fallback_definitions = {
            "uri": (
                limited_http_uri,
                "stdlib restricted absolute ASCII HTTP(S) URI; no userinfo/IRI/other schemes/IPv6 zones; not full RFC 3986",
                ["https://github.com/xiongcp/OpenBot", "https://example.com/a%20b?x=1#part", "http://[::1]:8080/"],
                ["not-a-uri", "https://example.com/a b", "https://example.com/%zz", "https://u:p@example.com/", "https://[::1", "https://example.com:99999/", "javascript:alert(1)"],
            ),
            "date-time": (
                limited_rfc3339_datetime,
                "stdlib restricted RFC 3339: offset required, years 0001..9999, no leap seconds",
                ["2026-11-05T12:00:00Z", "2024-02-29t12:00:00.123+08:00", "2026-11-05T00:00:00-00:00"],
                ["2026-02-29T12:00:00Z", "2026-11-05T12:00:00", "2026-11-05 12:00:00Z", "2026-11-05T24:00:00Z", "2026-11-05T12:00:60Z", "2026-11-05T12:00:00+08:99"],
            ),
        }
        for name in sorted(formats - checker.checkers.keys()):
            if name not in fallback_definitions:
                raise CheckSkipped(f"No registered or supported restricted validator for format {name}")
            function, description, valid, invalid = fallback_definitions[name]
            require(all(function(value) for value in valid) and all(not function(value) for value in invalid),
                    f"Restricted {name} checker sanity vectors failed")
            checker.checks(name)(function)
            format_modes[name] = description
            fallback_probes[name] = {"accepted_vectors": len(valid), "rejected_vectors": len(invalid)}
        module.Draft202012Validator.check_schema(schema)
        validator = module.Draft202012Validator(schema, format_checker=checker)
        errors = sorted(
            validator.iter_errors(self.document("website/releases.prelaunch.example.json")),
            key=lambda error: str(list(error.absolute_path)),
        )
        require(not errors, "; ".join(f"{list(error.absolute_path)}: {error.message}" for error in errors))
        return {
            "draft": "2020-12", "FormatChecker_enabled": True,
            "format_validators_available": sorted(formats), "external_refs_allowed": False,
            "format_validation_profile": format_modes,
            "restricted_checker_sanity_vectors": fallback_probes,
            "full_rfc_format_conformance_claimed": False,
            "validated_instance": "website/releases.prelaunch.example.json",
            "note": "Restricted fallback format profiles are explicit. Null release branches do not validate hypothetical release dates/assets or qualify any real product.",
        }

    def validate(self) -> dict[str, Any]:
        checks = [
            ("json_syntax", self.json_syntax),
            ("repo_collision_guard", self.repo_collision_guard),
            ("yaml_syntax", self.yaml_syntax),
            ("task_fields_and_ids", self.task_fields),
            ("dependency_dag", self.task_graph),
            ("rc_and_license_closure", self.release_closure),
            ("test_case_fields_ids_and_states", self.cases),
            ("gate_coverage_and_states", self.gates),
            ("source_index", self.sources),
            ("markdown_source_references", self.citations),
            ("prelaunch_manifest_semantics", self.prelaunch_manifest),
            ("website_json_schema_and_formats", self.website_schema),
        ]
        for name, action in checks:
            self.run_check(name, action)
        counts = Counter(check["status"] for check in self.checks)
        status = "FAIL" if counts["FAIL"] else "PARTIAL" if counts["SKIPPED"] else "PASS"
        script = Path(__file__).resolve()
        return {
            "schema_version": "1.1",
            "validation_kind": f"PLANNING_PACKAGE_{self.mode.upper()}_VALIDATION",
            "notice": "Only planning/execution package structure was checked. No OpenBot product test, native qualification, live integration, release or deployment was performed.",
            "product_tests_executed": False,
            "product_test_results_modified": False,
            "network_requests_performed": False,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "summary": {"checks": len(self.checks), "passed": counts["PASS"], "failed": counts["FAIL"], "skipped": counts["SKIPPED"]},
            "runtime": {"python": platform.python_version(), "optional_dependencies": self.optional_versions},
            "validator_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "checks": self.checks,
            "input_files": dict(sorted(self.inputs.items())),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Planning package root")
    parser.add_argument("--mode", choices=("plan", "execution", "rc"), default="plan", help="Validation stage mode")
    parser.add_argument("--no-write", action="store_true", help="Print checks without writing the JSON report")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"Package root does not exist: {args.root}")
    validator = PlanValidator(args.root, mode=args.mode)
    report = validator.validate()
    print(f"OpenBot plan package validation ({args.mode} mode) - NOT product testing")
    for check in report["checks"]:
        message = check.get("error") or check.get("reason")
        print(f"[{check['status']}] {check['id']}" + (f": {message}" if message else ""))
    summary = report["summary"]
    print(f"Result: {report['status']} | {summary['passed']} passed, {summary['failed']} failed, {summary['skipped']} skipped")
    if not args.no_write:
        target = validator.root / "evidence" / "package_validation.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Could not write report: {exc}", file=sys.stderr)
            return 1
        print(f"Report: {target}")
    return 1 if report["status"] == "FAIL" else 2 if report["status"] == "PARTIAL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
