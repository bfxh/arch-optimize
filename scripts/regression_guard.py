#!/usr/bin/env python3
"""arch-optimize: Regression Guard (Stage 5)

Runs test suites, compares before/after results, and calculates
zero-regression rate and EvoScore for evolution tracking.

Supports: go test, pytest, jest, cargo test
Dependencies: Python 3.8+ stdlib only

Usage:
    python3 regression_guard.py record --output baseline.json
    python3 regression_guard.py record --output current.json --test-cmd "go test ./... -v -json"
    python3 regression_guard.py compare --baseline baseline.json --current current.json
    python3 regression_guard.py compare --baseline baseline.json --current current.json --json
    python3 regression_guard.py evoscore --history history.json --gamma 1.5
"""

import argparse
import json
import os
import re
import subprocess
import sys

# ── Test command auto-detection ─────────────────────────────────────

def detect_test_cmd(cwd: str = ".") -> str:
    """Auto-detect test command based on project files present."""
    # Go
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return "go test ./... -v -json"
    # Python / pytest
    if os.path.exists(os.path.join(cwd, "pytest.ini")) or os.path.exists(os.path.join(cwd, "setup.cfg")):
        return "python -m pytest --tb=short -v"
    pyproject = os.path.join(cwd, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r", encoding="utf-8", errors="replace") as f:
                if "[tool.pytest" in f.read():
                    return "python -m pytest --tb=short -v"
        except Exception:
            pass
    # JavaScript / jest
    pkg_json = os.path.join(cwd, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8", errors="replace") as f:
                pkg = json.load(f)
                deps = {}
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                if "jest" in deps:
                    return "npx jest --json"
        except Exception:
            pass
    # Rust / cargo
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return "cargo test -- --nocapture"
    return ""


# ── Test output parsers ─────────────────────────────────────────────

def parse_go_test_json(output: str) -> dict:
    """Parse `go test -json` output. Each line is a JSON object."""
    results = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        test_name = entry.get("Test")
        action = entry.get("Action")
        if not test_name or action not in ("pass", "fail"):
            continue
        elapsed = entry.get("Elapsed", 0)
        duration_ms = int(elapsed * 1000) if elapsed else 0
        results[test_name] = {
            "status": "pass" if action == "pass" else "fail",
            "duration_ms": duration_ms,
        }
    return results


def parse_pytest_verbose(output: str) -> dict:
    """Parse `pytest -v` output for PASSED/FAILED/ERROR lines."""
    results = {}
    pattern = re.compile(r"^(.+?)\s+(PASSED|FAILED|ERROR|SKIPPED)\b")
    for line in output.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        test_name = m.group(1).strip()
        status_raw = m.group(2)
        status_map = {"PASSED": "pass", "FAILED": "fail", "ERROR": "fail", "SKIPPED": "skip"}
        status = status_map.get(status_raw, "skip")
        if status == "skip":
            continue
        results[test_name] = {"status": status, "duration_ms": 0}
    return results


def parse_jest_json(output: str) -> dict:
    """Parse `jest --json` output."""
    results = {}
    data = None
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        idx = output.find("{")
        if idx >= 0:
            try:
                data = json.loads(output[idx:])
            except json.JSONDecodeError:
                data = None
    if data is None:
        return results
    for test_suite in data.get("testResults", []):
        for assertion in test_suite.get("assertionResults", []):
            full_name = assertion.get("fullName") or assertion.get("title", "")
            status = assertion.get("status", "skipped")
            duration = assertion.get("duration", 0) or 0
            if status in ("passed", "failed"):
                results[full_name] = {
                    "status": "pass" if status == "passed" else "fail",
                    "duration_ms": int(duration),
                }
    return results


def parse_cargo_test(output: str) -> dict:
    """Parse `cargo test` output."""
    results = {}
    pattern = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+(ok|FAILED|ignored)")
    for line in output.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        test_name = m.group(1)
        status_raw = m.group(2)
        if status_raw == "ignored":
            continue
        results[test_name] = {
            "status": "pass" if status_raw == "ok" else "fail",
            "duration_ms": 0,
        }
    return results


def parse_test_output(output: str, test_cmd: str) -> dict:
    """Auto-detect parser based on command and output content."""
    cmd_lower = test_cmd.lower()
    if "go test" in cmd_lower and "-json" in cmd_lower:
        return parse_go_test_json(output)
    if "pytest" in cmd_lower:
        return parse_pytest_verbose(output)
    if "jest" in cmd_lower and "--json" in cmd_lower:
        return parse_jest_json(output)
    if "cargo test" in cmd_lower:
        return parse_cargo_test(output)
    # Heuristic fallback based on content
    stripped = output.lstrip()
    if stripped.startswith("{"):
        first_line = output.splitlines()[0].strip() if output.strip() else ""
        if '"Action"' in first_line:
            return parse_go_test_json(output)
        try:
            json.loads(output)
            return parse_jest_json(output)
        except json.JSONDecodeError:
            return parse_go_test_json(output)
    if "PASSED" in output or "FAILED" in output:
        return parse_pytest_verbose(output)
    if re.search(r"test\s+\S+\s+\.\.\.\s+(ok|FAILED)", output):
        return parse_cargo_test(output)
    return {}


# ── record subcommand ───────────────────────────────────────────────

def run_tests(test_cmd: str, cwd: str = ".") -> dict:
    """Run test command and return parsed results."""
    try:
        proc = subprocess.run(
            test_cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        output = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return {"error": "Test command timed out after 600s", "command": test_cmd}
    except Exception as e:
        return {"error": f"Failed to run test command: {e}", "command": test_cmd}

    results = parse_test_output(output, test_cmd)
    return {
        "command": test_cmd,
        "results": results,
        "total": len(results),
        "passed": sum(1 for r in results.values() if r["status"] == "pass"),
        "failed": sum(1 for r in results.values() if r["status"] == "fail"),
    }


def cmd_record(args) -> int:
    """Record test results to a JSON file."""
    test_cmd = args.test_cmd
    if not test_cmd:
        test_cmd = detect_test_cmd(args.cwd)
        if not test_cmd:
            print("Error: Could not auto-detect test command. Use --test-cmd to specify.", file=sys.stderr)
            return 1
        print(f"Auto-detected test command: {test_cmd}", file=sys.stderr)

    data = run_tests(test_cmd, args.cwd)
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        return 1

    output_data = {
        "command": data["command"],
        "total": data["total"],
        "passed": data["passed"],
        "failed": data["failed"],
        "results": data["results"],
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Recorded {data['total']} tests ({data['passed']} passed, {data['failed']} failed) to {args.output}")
    return 0


# ── compare subcommand ─────────────────────────────────────────────

def compare_results(baseline: dict, current: dict) -> dict:
    """Compare baseline and current test results."""
    base_tests = baseline.get("results", {})
    curr_tests = current.get("results", {})

    regressions = []
    improvements = []
    new_tests = []
    removed_tests = []
    perf_regressions = []

    all_names = set(base_tests.keys()) | set(curr_tests.keys())

    for name in sorted(all_names):
        b = base_tests.get(name)
        c = curr_tests.get(name)
        if b and c:
            if b["status"] == "pass" and c["status"] == "fail":
                regressions.append({"test": name, "was": "PASS", "now": "FAIL"})
            elif b["status"] == "fail" and c["status"] == "pass":
                improvements.append({"test": name, "was": "FAIL", "now": "PASS"})
            # Performance regression: duration increased >10%
            b_dur = b.get("duration_ms", 0)
            c_dur = c.get("duration_ms", 0)
            if b_dur > 0 and c_dur > 0:
                increase = (c_dur - b_dur) / b_dur
                if increase > 0.10:
                    perf_regressions.append({
                        "test": name,
                        "was_ms": b_dur,
                        "now_ms": c_dur,
                        "increase_pct": round(increase * 100, 1),
                    })
        elif c and not b:
            new_tests.append(name)
        elif b and not c:
            removed_tests.append(name)

    # Zero-regression rate
    total_tasks = len(all_names)
    regression_count = len(regressions)
    zero_reg_rate = ((total_tasks - regression_count) / total_tasks * 100) if total_tasks > 0 else 100.0

    # Non-asymmetric scoring
    baseline_pass = baseline.get("passed", sum(1 for r in base_tests.values() if r["status"] == "pass"))
    new_pass = current.get("passed", sum(1 for r in curr_tests.values() if r["status"] == "pass"))
    target_pass = baseline_pass + max(1, len(new_tests))

    if new_pass >= baseline_pass and target_pass > baseline_pass:
        improvement_score = (new_pass - baseline_pass) / (target_pass - baseline_pass)
    else:
        improvement_score = 0.0
    regression_penalty = regression_count / baseline_pass if baseline_pass > 0 else 0.0
    total_score = improvement_score - regression_penalty * 2

    # Health score (soft gate): 100 - 15*Critical - 5*Warning
    critical = regression_count
    warning = len(perf_regressions)
    health_score = max(0, 100 - 15 * critical - 5 * warning)

    # Gate logic
    hard_gate_passed = regression_count == 0
    soft_gate_passed = health_score >= 70
    gate_passed = hard_gate_passed

    if not hard_gate_passed:
        gate_reason = f"{regression_count} regression(s) detected (hard gate failed)"
    elif not soft_gate_passed:
        gate_reason = f"Zero regression rate = {zero_reg_rate:.1f}% (soft gate: health={health_score} < 70)"
    else:
        gate_reason = f"Zero regression rate = {zero_reg_rate:.1f}%"

    # Findings with severity
    findings = []
    for r in regressions:
        findings.append({
            "severity": "Critical",
            "issue": "REGRESSION",
            "test": r["test"],
            "detail": f"{r['was']} -> {r['now']}",
        })
    for p in perf_regressions:
        findings.append({
            "severity": "Warning",
            "issue": "PERFORMANCE_REGRESSION",
            "test": p["test"],
            "detail": f"{p['was_ms']}ms -> {p['now_ms']}ms (+{p['increase_pct']}%)",
        })

    return {
        "baseline": {
            "total": baseline.get("total", len(base_tests)),
            "passed": baseline_pass,
            "failed": baseline.get("failed", len(base_tests) - baseline_pass),
        },
        "current": {
            "total": current.get("total", len(curr_tests)),
            "passed": new_pass,
            "failed": current.get("failed", len(curr_tests) - new_pass),
        },
        "regressions": regressions,
        "improvements": improvements,
        "new_tests": new_tests,
        "removed_tests": removed_tests,
        "performance_regressions": perf_regressions,
        "zero_regression_rate": round(zero_reg_rate, 1),
        "non_asymmetric_score": round(total_score, 4),
        "health_score": health_score,
        "gate_passed": gate_passed,
        "gate_reason": gate_reason,
        "findings": findings,
    }


def cmd_compare(args) -> int:
    """Compare baseline and current test results."""
    try:
        with open(args.baseline, "r", encoding="utf-8") as f:
            baseline = json.load(f)
    except Exception as e:
        print(f"Error reading baseline: {e}", file=sys.stderr)
        return 1
    try:
        with open(args.current, "r", encoding="utf-8") as f:
            current = json.load(f)
    except Exception as e:
        print(f"Error reading current: {e}", file=sys.stderr)
        return 1

    result = compare_results(baseline, current)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human_compare(result)

    return 0 if result["gate_passed"] else 1


def print_human_compare(result: dict):
    """Print human-readable comparison report."""
    b = result["baseline"]
    c = result["current"]
    print(f"\n{'='*60}")
    print(f"  arch-optimize Regression Guard - Comparison Report")
    print(f"{'='*60}")
    print(f"  {'Metric':<30s} {'Baseline':>12s} {'Current':>12s}")
    print(f"  {'-'*56}")
    print(f"  {'Total tests':<30s} {b['total']:>12d} {c['total']:>12d}")
    print(f"  {'Passed':<30s} {b['passed']:>12d} {c['passed']:>12d}")
    print(f"  {'Failed':<30s} {b['failed']:>12d} {c['failed']:>12d}")
    print(f"{'='*60}")
    print(f"  Regressions:           {len(result['regressions'])}")
    print(f"  Improvements:          {len(result['improvements'])}")
    print(f"  New tests:             {len(result['new_tests'])}")
    print(f"  Removed tests:         {len(result['removed_tests'])}")
    print(f"  Perf regressions:      {len(result['performance_regressions'])}")
    print(f"  Zero-regression rate:  {result['zero_regression_rate']}%")
    print(f"  Non-asymmetric score:  {result['non_asymmetric_score']}")
    print(f"  Health score:          {result['health_score']}/100")

    if result["regressions"]:
        print(f"\n  {'-'*56}")
        print(f"  REGRESSIONS (Critical):")
        for r in result["regressions"]:
            print(f"    {r['test']}: {r['was']} -> {r['now']}")

    if result["performance_regressions"]:
        print(f"\n  {'-'*56}")
        print(f"  PERFORMANCE REGRESSIONS (Warning):")
        for p in result["performance_regressions"]:
            print(f"    {p['test']}: {p['was_ms']}ms -> {p['now_ms']}ms (+{p['increase_pct']}%)")

    if result["improvements"]:
        print(f"\n  {'-'*56}")
        print(f"  IMPROVEMENTS:")
        for i in result["improvements"]:
            print(f"    {i['test']}: {i['was']} -> {i['now']}")

    print(f"\n{'='*60}")
    status = "PASSED" if result["gate_passed"] else "FAILED"
    print(f"  Gate: {status} - {result['gate_reason']}")
    print(f"{'='*60}\n")


# ── evoscore subcommand ─────────────────────────────────────────────

def calculate_evoscore(history: list, gamma: float = 1.5) -> dict:
    """
    Calculate EvoScore from iteration history.

    EvoScore = Sum(gamma^i * a(c_i)) / Sum(gamma^i)
    where a(c) = (n(c) - n(c_0)) / (n(c_*) - n(c_0)) if improved,
                 else (n(c) - n(c_0)) / n(c_0)
    """
    if not history:
        return {"evoscore": 0.0, "trend": "stable", "warning": "Empty history"}

    sorted_hist = sorted(history, key=lambda x: x.get("iteration", 0))
    c_0 = sorted_hist[0]
    n_c0 = c_0.get("passed", 0)

    target = max((h.get("target", 0) for h in sorted_hist), default=0)
    if target <= n_c0:
        target = n_c0 + 1

    numerator = 0.0
    denominator = 0.0
    iteration_scores = []

    for i, entry in enumerate(sorted_hist):
        n_ci = entry.get("passed", 0)
        improved = n_ci > n_c0
        if improved:
            denom_val = target - n_c0
            a_ci = (n_ci - n_c0) / denom_val if denom_val > 0 else 0.0
        else:
            a_ci = (n_ci - n_c0) / n_c0 if n_c0 > 0 else 0.0
        weight = gamma ** i
        numerator += weight * a_ci
        denominator += weight
        iteration_scores.append({
            "iteration": entry.get("iteration", i + 1),
            "passed": n_ci,
            "regressions": entry.get("regressions", 0),
            "a_score": round(a_ci, 4),
            "weight": round(weight, 4),
        })

    evoscore = numerator / denominator if denominator > 0 else 0.0

    # Trend detection
    trend = "stable"
    if len(sorted_hist) >= 2:
        recent = [h.get("passed", 0) for h in sorted_hist[-3:]]
        if len(recent) >= 2:
            if recent[-1] > recent[0]:
                trend = "improving"
            elif recent[-1] < recent[0]:
                trend = "declining"

    # Consecutive regressions warning
    consecutive = 0
    max_consecutive = 0
    for h in sorted_hist:
        if h.get("regressions", 0) > 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0

    warning = None
    if max_consecutive >= 2:
        warning = f"Detected {max_consecutive} consecutive iterations with regressions"

    return {
        "evoscore": round(evoscore, 4),
        "trend": trend,
        "gamma": gamma,
        "iterations": len(sorted_hist),
        "baseline_passed": n_c0,
        "target_passed": target,
        "iteration_scores": iteration_scores,
        "max_consecutive_regressions": max_consecutive,
        "warning": warning,
    }


def cmd_evoscore(args) -> int:
    """Calculate EvoScore from history file."""
    try:
        with open(args.history, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception as e:
        print(f"Error reading history: {e}", file=sys.stderr)
        return 1

    if not isinstance(history, list):
        print("Error: History file must contain a JSON array", file=sys.stderr)
        return 1

    result = calculate_evoscore(history, args.gamma)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"  arch-optimize EvoScore Report")
        print(f"{'='*60}")
        print(f"  Gamma:                {result['gamma']}")
        print(f"  Iterations:           {result['iterations']}")
        print(f"  Baseline passed:      {result['baseline_passed']}")
        print(f"  Target passed:        {result['target_passed']}")
        print(f"  EvoScore:             {result['evoscore']}")
        print(f"  Trend:                {result['trend']}")
        print(f"  Max consecutive reg.:  {result['max_consecutive_regressions']}")
        if result.get("warning"):
            print(f"  WARNING:              {result['warning']}")
        print(f"\n  {'-'*56}")
        print(f"  {'Iter':<6s} {'Passed':<10s} {'Regress':<10s} {'a(c)':<10s} {'Weight':<10s}")
        print(f"  {'-'*56}")
        for s in result["iteration_scores"]:
            print(f"  {s['iteration']:<6d} {s['passed']:<10d} {s['regressions']:<10d} {s['a_score']:<10.4f} {s['weight']:<10.4f}")
        print(f"{'='*60}\n")

    return 0


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="arch-optimize: Regression Guard (Stage 5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s record --output baseline.json
  %(prog)s record --output current.json --test-cmd "go test ./... -v -json"
  %(prog)s compare --baseline baseline.json --current current.json
  %(prog)s compare --baseline baseline.json --current current.json --json
  %(prog)s evoscore --history history.json --gamma 1.5
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # record
    p_record = subparsers.add_parser("record", help="Record test results to JSON")
    p_record.add_argument("--output", required=True, help="Output JSON file path")
    p_record.add_argument("--test-cmd", default=None, help="Test command to run (auto-detected if omitted)")
    p_record.add_argument("--cwd", default=".", help="Working directory for test command")
    p_record.set_defaults(func=cmd_record)

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare baseline vs current test results")
    p_compare.add_argument("--baseline", required=True, help="Baseline JSON file")
    p_compare.add_argument("--current", required=True, help="Current JSON file")
    p_compare.add_argument("--json", action="store_true", help="Output as JSON")
    p_compare.set_defaults(func=cmd_compare)

    # evoscore
    p_evoscore = subparsers.add_parser("evoscore", help="Calculate EvoScore from history")
    p_evoscore.add_argument("--history", required=True, help="History JSON file (array of iterations)")
    p_evoscore.add_argument("--gamma", type=float, default=1.5, help="Discount factor (default: 1.5)")
    p_evoscore.add_argument("--json", action="store_true", help="Output as JSON")
    p_evoscore.set_defaults(func=cmd_evoscore)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
