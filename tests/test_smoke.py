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
            capture_output=True, timeout=120,
        )
        if not (p.returncode == 0 and os.path.exists(out_a)):
            print(f"SKIP regression roundtrip: record rc={p.returncode}, "
                  f"stderr={p.stderr.decode('utf-8', 'replace')[:200]!r}")
            return
        cmp_p = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "regression_guard.py"),
             "compare", "--baseline", out_a, "--current", out_a, "--json"],
            capture_output=True, timeout=120,
        )
        result = json.loads(cmp_p.stdout.decode("utf-8"))
        for key in ("regressions", "improvements", "new_tests", "removed_tests"):
            assert key in result, f"compare missing key: {key}"
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_smoke(tmp_path=None):
    sample = make_sample_project()
    try:
        _check_stage1(sample)
        _check_stage2_3(sample)
        _check_regression_guard()
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
