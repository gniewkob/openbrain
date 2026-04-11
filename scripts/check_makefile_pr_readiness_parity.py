#!/usr/bin/env python3
"""Guardrail: keep Makefile pytest targets aligned with PR readiness bundles."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PR_READINESS = ROOT / "scripts" / "check_pr_readiness.py"
MAKEFILE = ROOT / "Makefile"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_pr_step_tests(source: str, step_label: str) -> set[str]:
    tree = ast.parse(source)
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            if any(
                isinstance(t, ast.Name) and t.id == "PR_READINESS_STEPS"
                for t in node.targets
            ):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "PR_READINESS_STEPS":
                value = node.value
        if value is None:
            continue
        if not isinstance(value, ast.Tuple):
            raise ValueError("PR_READINESS_STEPS must be a tuple")
        for step in value.elts:
            if not isinstance(step, ast.Tuple) or len(step.elts) != 2:
                continue
            label_node, cmd_node = step.elts
            if not (isinstance(label_node, ast.Constant) and isinstance(label_node.value, str)):
                continue
            if label_node.value != step_label:
                continue
            if not isinstance(cmd_node, ast.List):
                raise ValueError(f"{step_label} command must be a list")
            tests: set[str] = set()
            for elt in cmd_node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    value = elt.value
                    if value.startswith("unified/") and value.endswith(".py"):
                        tests.add(value)
            return tests
    raise ValueError(f"{step_label} not found in PR_READINESS_STEPS")


def _extract_make_target_tests(source: str, target_name: str) -> set[str]:
    lines = source.splitlines()
    header = f"{target_name}:"
    start_idx = -1
    for idx, line in enumerate(lines):
        if line.startswith(header):
            start_idx = idx
            break
    if start_idx == -1:
        raise ValueError(f"target {target_name} not found in Makefile")

    command_lines: list[str] = []
    for line in lines[start_idx + 1 :]:
        if line.startswith("\t"):
            command_lines.append(line)
            continue
        if line.strip() == "":
            continue
        # Next target or top-level directive.
        break

    text = "\n".join(command_lines)
    matches = re.findall(r"(unified/[^\s\\]+\.py)", text)
    return set(matches)


def _check_parity(pr_source: str, make_source: str) -> list[str]:
    errors: list[str] = []
    mappings = (
        ("guardrail runner tests", "guardrail-tests"),
        ("contract integrity smoke", "contract-smoke"),
    )
    for step_label, target_name in mappings:
        pr_tests = _extract_pr_step_tests(pr_source, step_label)
        make_tests = _extract_make_target_tests(make_source, target_name)
        if pr_tests != make_tests:
            missing_in_make = sorted(pr_tests - make_tests)
            missing_in_pr = sorted(make_tests - pr_tests)
            errors.append(
                f"{target_name} drift vs '{step_label}': "
                f"missing_in_make={missing_in_make} missing_in_pr={missing_in_pr}"
            )
    return errors


def main() -> int:
    try:
        pr_source = PR_READINESS.read_text(encoding="utf-8")
        make_source = MAKEFILE.read_text(encoding="utf-8")
        errors = _check_parity(pr_source, make_source)
    except Exception as exc:
        _fail(f"makefile pr-readiness parity: {exc}")
        return 1
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Makefile and PR readiness parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
