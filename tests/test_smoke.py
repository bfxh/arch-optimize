#!/usr/bin/env python3
"""Smoke tests: each script runs against a sample project and emits valid JSON.

Zero external dependencies. Run either way:
    python tests/test_smoke.py          # standalone, exit code 0/1
    python -m pytest tests/             # if pytest is installed
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

SAMPLE_FILES = {
    # Two packages so dep_graph can see a cross-module import.
    "pkg_a/main.py": (
        '"""Sample app entry."""\n'
        "from pkg_b.helper import calc\n"
        "\n"
        "def run(values):\n"
        "    total = 0\n"
        "    for v in values:\n"
        "        total = calc(total, v)\n"
        "    return total\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    print(run([1, 2, 3]))\n"
    ),
    "pkg_b/helper.py": (
        '"""Arithmetic helpers."""\n'
        "\n"
        "def calc(acc, x):\n"
        '    """Add x onto acc."""\n'
        "    return acc + x\n"
        "\n"
        "def unused_helper(x):\n"
        '    """Defined but never called anywhere."""\n'
        "    return x * 2\n"
    ),
}


def make_sample_project():
    tmp = tempfile.mkdtemp(prefix="arch-opt-smoke-")
    for rel, content in SAMPLE_FILES.items():
        path = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return tmp


def run_script(name, *args):
    p = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, name), *args],
        capture_output=True,
        timeout=120,
        check=False,  # 断言在下一行按 returncode 判定
    )
    assert p.returncode == 0, (
        f"{name} exited {p.returncode}\nstdout: {p.stdout[:500]!r}\nstderr: {p.stderr[:500]!r}"
    )
    return json.loads(p.stdout.decode("utf-8"))


def _check_stage1(sample):
    scan = run_script("arch_scan.py", "--target", sample, "--json")
    for key in ("directory_tree", "entry_points", "modules"):
        assert key in scan, f"arch_scan missing key: {key}"

    dep = run_script("dep_graph.py", "--target", sample, "--json")
    for key in ("modules", "edges", "circular_deps", "mermaid"):
        assert key in dep, f"dep_graph missing key: {key}"
    edges = {(e["from"], e["to"]) for e in dep.get("edges", [])}
    assert ("pkg_a", "pkg_b") in edges, f"expected pkg_a->pkg_b edge, got {sorted(edges)}"


def _check_stage2_3(sample):
    diag = run_script("risk_diagnose.py", "--target", sample, "--json")
    for key in ("findings", "findings_by_risk", "health_score", "risks_scanned"):
        assert key in diag, f"risk_diagnose missing key: {key}"
    assert set(diag["risks_scanned"]) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert diag == run_script("risk_diagnose.py", "--target", sample, "--json"), \
        "risk_diagnose should be deterministic"

    qual = run_script("quality_metrics.py", "--target", sample, "--json")
    for key in ("files", "health_score", "average_cc"):
        assert key in qual, f"quality_metrics missing key: {key}"
    assert qual["files_analyzed"] >= 1


def _check_regression_guard():
    out_dir = tempfile.mkdtemp(prefix="arch-opt-rg-")
    out_a = os.path.join(out_dir, "baseline.json")
    fake_test = f'"{sys.executable}" -c "print(\'t.py::test_alpha PASSED\')"'
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "regression_guard.py"),
             "record", "--output", out_a, "--test-cmd", fake_test],
            capture_output=True, timeout=120, check=False,
        )
        # record 失败必须让测试失败，不允许静默跳过（否则阶段五永远不被验证）
        assert p.returncode == 0 and os.path.exists(out_a), (
            f"record failed: rc={p.returncode}, "
            f"stderr={p.stderr.decode('utf-8', 'replace')[:300]!r}")
        cmp_p = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "regression_guard.py"),
             "compare", "--baseline", out_a, "--current", out_a, "--json"],
            capture_output=True, timeout=120, check=False,
        )
        result = json.loads(cmp_p.stdout.decode("utf-8"))
        for key in ("regressions", "improvements", "new_tests", "removed_tests"):
            assert key in result, f"compare missing key: {key}"
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _fake_pytest_cmd(lines):
    """Build a --test-cmd that emits pytest -v style lines."""
    prog = ";".join(f"print({line!r})" for line in lines)
    return f'"{sys.executable}" -c "{prog}"'


def _check_regression_is_detected():
    """核心断言：pass -> fail 必须被判为回归且 compare 退出码为 1。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-reg-")
    base = os.path.join(out_dir, "baseline.json")
    cur = os.path.join(out_dir, "current.json")
    rg = os.path.join(SCRIPTS, "regression_guard.py")
    try:
        for out, lines in ((base, ["t.py::test_a PASSED", "t.py::test_b PASSED"]),
                           (cur, ["t.py::test_a FAILED", "t.py::test_b PASSED"])):
            p = subprocess.run(
                [sys.executable, rg, "record", "--output", out,
                 "--test-cmd", _fake_pytest_cmd(lines)],
                capture_output=True, timeout=120, check=False)
            assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[:300]
        cmp_p = subprocess.run(
            [sys.executable, rg, "compare", "--baseline", base, "--current", cur,
             "--json"],
            capture_output=True, timeout=120, check=False)
        result = json.loads(cmp_p.stdout.decode("utf-8"))
        regressed = {r["test"] for r in result["regressions"]}
        assert "t.py::test_a" in regressed, (
            f"真实回归未被判出（gate_passed={result['gate_passed']}）")
        assert result["gate_passed"] is False, "有回归时 gate_passed 必须为 False"
        assert cmp_p.returncode == 1, (
            f"有回归时 compare 退出码必须为 1，实际 {cmp_p.returncode}")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


EXPECTED_FLAGS = {
    "arch_scan.py": {"--target", "--json", "--depth"},
    "dep_graph.py": {"--target", "--json", "--output", "--format", "--max-depth"},
    "risk_diagnose.py": {"--target", "--file", "--json", "--risk", "--min-severity"},
    "quality_metrics.py": {"--target", "--file", "--json", "--min-cc", "--quiet"},
    "regression_guard.py": {"--output", "--test-cmd", "--cwd", "--baseline",
                            "--current", "--history", "--gamma", "--json"},
}

DOC_SUBCOMMANDS = {"regression_guard.py": ["record", "compare", "evoscore"]}

GHOST_SCRIPTS = ("check_regression.py", "calculate_mi.py", "health_score.py")
DOC_PATHS = ("SKILL.md", "README.md")


def _help_flags(script, subcommand=None):
    args = [sys.executable, os.path.join(SCRIPTS, script), "--help"]
    if subcommand:
        args = [sys.executable, os.path.join(SCRIPTS, script), subcommand, "--help"]
    p = subprocess.run(args, capture_output=True, timeout=120, check=False)
    text = p.stdout.decode("utf-8", "replace")
    return ({tok.split("=")[0] for tok in text.split() if tok.startswith("--")}
            - {"--help"})


def _check_cli_surface_matches_docs():
    """文档里的参数面必须等于 argparse 的真实参数面。"""
    import re
    for script, expected in EXPECTED_FLAGS.items():
        actual = _help_flags(script)
        for sub in DOC_SUBCOMMANDS.get(script, ()):
            actual |= _help_flags(script, sub) - {"--help"}
        assert actual == expected, (
            f"{script} 参数面漂移：文档口径 {sorted(expected)}，"
            f"实际 {sorted(actual)}，差集 {sorted(actual ^ expected)}")

    known = {s: set(f) for s, f in EXPECTED_FLAGS.items()}
    for name in DOC_PATHS:
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            text = fh.read()
        for ghost in GHOST_SCRIPTS:
            assert ghost not in text, f"{name} 引用了不存在的脚本 {ghost}"
        assert "Python 3.8" not in text and "3.8+" not in text, \
            f"{name} 仍声明未被 CI 覆盖的旧 Python 版本"
        for line in text.split("\n"):
            for script in known:
                if script not in line:
                    continue
                for flag in re.findall(r"--[a-z][a-z-]*", line):
                    assert flag in known[script], (
                        f"{name} 给 {script} 用了它没有的参数 {flag}")


def test_smoke(tmp_path=None):
    sample = make_sample_project()
    try:
        _check_stage1(sample)
        _check_stage2_3(sample)
        _check_regression_guard()
        _check_regression_is_detected()
        _check_cli_surface_matches_docs()
    finally:
        shutil.rmtree(sample, ignore_errors=True)


# --- standalone runner -------------------------------------------------

def _standalone():
    try:
        test_smoke()
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e!r}")
        sys.exit(1)
    print("all smoke tests passed")


if __name__ == "__main__":
    _standalone()
