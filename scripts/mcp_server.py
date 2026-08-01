#!/usr/bin/env python3
"""arch-optimize MCP Server

Exposes 5 architecture analysis tools via the Model Context Protocol (MCP)
so that AI agents can invoke the arch-optimize CLI scripts as structured
tools.

Tools:
    arch_optimize_scan             - Architecture perception (Stage 1)
    arch_optimize_dep_graph        - Dependency graph generation (Stage 1)
    arch_optimize_risk_diagnose    - R1-R6 risk diagnosis (Stage 2)
    arch_optimize_quality_metrics  - Quality metrics calculation (Stage 3)
    arch_optimize_regression_guard - Regression detection (Stage 5)

Design: Each tool wraps an existing CLI script via subprocess, passing the
``--json`` flag so that structured JSON is returned. Scripts stay
self-contained and no import-path coupling is introduced.

Environment: Python 3.10+, ``mcp`` package v1.28.1 (FastMCP from
``mcp.server.fastmcp``). NOTE: mcp 2.x removed FastMCP; install mcp<2:
    pip install "mcp>=1.28.1,<2"
"""

import json
import os
import subprocess
import sys
from typing import Annotated, Literal, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        'mcp_server.py 需要 mcp<2（FastMCP API）：pip install "mcp>=1.28.1,<2"',
        file=sys.stderr,
    )
    sys.exit(1)
from pydantic import Field

# ── Setup ──────────────────────────────────────────────────────────────────

# Directory containing this file and the wrapped CLI scripts.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Default subprocess timeout (seconds). The ``record`` action runs real test
# suites and uses a larger timeout (see arch_optimize_regression_guard).
DEFAULT_TIMEOUT = 300
RECORD_TIMEOUT = 900

mcp = FastMCP("arch_optimize")


# ── Helper ─────────────────────────────────────────────────────────────────


def _run_script(script_name: str, args: list, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run a CLI script with args and return its stdout as a string.

    On non-zero exit codes the result is a JSON object with an ``error``
    field so that tool callers can reliably parse failures.
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {"error": f"Script execution timed out ({timeout}s)"},
            ensure_ascii=False,
        )
    except Exception as e:  # pragma: no cover - defensive
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    if proc.returncode != 0:
        return json.dumps(
            {
                "error": proc.stderr.strip() or proc.stdout.strip() or "Unknown error",
                "returncode": proc.returncode,
            },
            ensure_ascii=False,
        )
    return proc.stdout


# ── Tool 1: Architecture Scan (Stage 1) ────────────────────────────────────


@mcp.tool(
    name="arch_optimize_scan",
    annotations={
        "title": "Architecture Scan",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def arch_optimize_scan(
    target: Annotated[str, Field(description="Project root directory to scan", min_length=1)],
    depth: Annotated[int, Field(description="Maximum directory scan depth", ge=1, le=20)] = 5,
) -> str:
    """Scan project architecture: directory tree, entry points, tech stack,
    modules, and architecture docs (Stage 1 - Architecture Perception).

    Args:
        target: Project root directory path.
        depth: Maximum scan depth (default 5, range 1-20).

    Returns:
        JSON string with keys: directory_tree, entry_points, tech_stack,
        modules, architecture_docs, summary.
    """
    return _run_script(
        "arch_scan.py",
        ["--target", target, "--depth", str(depth), "--json"],
    )


# ── Tool 2: Dependency Graph (Stage 1) ─────────────────────────────────────


@mcp.tool(
    name="arch_optimize_dep_graph",
    annotations={
        "title": "Dependency Graph",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def arch_optimize_dep_graph(
    target: Annotated[str, Field(description="Source directory to analyze", min_length=1)],
    format: Annotated[Literal["mermaid", "dot"], Field(description="Graph output format")] = "mermaid",
    max_depth: Annotated[int, Field(description="Maximum directory depth to scan (0 = unlimited)", ge=0)] = 0,
) -> str:
    """Generate a module dependency graph and detect circular dependencies
    (Stage 1 - Architecture Perception).

    Args:
        target: Source directory to analyze.
        format: Graph format - "mermaid" or "dot" (default "mermaid").
        max_depth: Maximum directory depth to scan; 0 means unlimited.

    Returns:
        JSON string with keys: modules, edges, circular_deps, mermaid, dot.
        Both mermaid and dot graph strings are always included in the JSON
        output regardless of the ``format`` argument.
    """
    return _run_script(
        "dep_graph.py",
        [
            "--target", target,
            "--format", format,
            "--max-depth", str(max_depth),
            "--json",
        ],
    )


# ── Tool 3: Risk Diagnosis (Stage 2) ───────────────────────────────────────


@mcp.tool(
    name="arch_optimize_risk_diagnose",
    annotations={
        "title": "Risk Diagnosis",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def arch_optimize_risk_diagnose(
    target: Annotated[str, Field(description="Project directory to diagnose", min_length=1)],
    risk: Annotated[
        Optional[Literal["R1", "R2", "R3", "R4", "R5", "R6"]],
        Field(description="Filter by a single risk type; omit to scan all R1-R6"),
    ] = None,
    min_severity: Annotated[
        Optional[Literal["Critical", "Warning", "Suggestion"]],
        Field(description="Minimum severity to report; omit to report all severities"),
    ] = None,
) -> str:
    """Diagnose six architectural decay risks (R1-R6) using the four-part
    Symptom -> Source -> Consequence -> Remedy format (Stage 2).

    Risks:
        R1 Cognitive Overload, R2 Change Propagation, R3 Knowledge Duplication,
        R4 Accidental Complexity, R5 Dependency Disorder, R6 Domain Model
        Distortion.

    Args:
        target: Project directory to diagnose.
        risk: Scan only this risk type (e.g. "R5"); omit to scan all six.
        min_severity: Minimum severity to report ("Critical", "Warning", or
            "Suggestion"); omit to report all severities.

    Returns:
        JSON string with keys: findings (each has risk, severity, location,
        symptom, source, consequence, remedy), health_score, findings_by_risk.
    """
    args = ["--target", target]
    if risk is not None:
        args += ["--risk", risk]
    if min_severity is not None:
        args += ["--min-severity", min_severity]
    args.append("--json")
    return _run_script("risk_diagnose.py", args)


# ── Tool 4: Quality Metrics (Stage 3) ──────────────────────────────────────


@mcp.tool(
    name="arch_optimize_quality_metrics",
    annotations={
        "title": "Quality Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def arch_optimize_quality_metrics(
    target: Annotated[Optional[str], Field(description="Directory to analyze")] = None,
    file: Annotated[Optional[str], Field(description="Single source file to analyze")] = None,
    min_cc: Annotated[int, Field(description="Only report functions with CC >= this value (0 = no filter)", ge=0)] = 0,
) -> str:
    """Calculate Maintainability Index (MI), Cyclomatic Complexity (CC),
    Halstead Volume, and HealthScore (Stage 3).

    Either ``target`` (directory) or ``file`` (single file) must be provided.

    Args:
        target: Directory to analyze (mutually exclusive with ``file``).
        file: Single source file to analyze (mutually exclusive with ``target``).
        min_cc: Minimum cyclomatic complexity to report per function
            (default 0, meaning no filtering).

    Returns:
        JSON string with keys: average_mi, average_cc, health_score,
        hotspots, files (per-file metrics).
    """
    args: list = []
    if file:
        args += ["--file", file]
    elif target:
        args += ["--target", target]
    else:
        return json.dumps(
            {"error": "Either 'target' or 'file' must be provided"},
            ensure_ascii=False,
        )
    if min_cc > 0:
        args += ["--min-cc", str(min_cc)]
    args.append("--json")
    return _run_script("quality_metrics.py", args)


# ── Tool 5: Regression Guard (Stage 5) ─────────────────────────────────────


@mcp.tool(
    name="arch_optimize_regression_guard",
    annotations={
        "title": "Regression Guard",
        "readOnlyHint": False,
        # 安全：test_cmd 会以 shell=True 执行任意命令（stdio 本地信任模型内为设计能力，
        # 但必须让客户端做破坏性确认；若改 HTTP/SSE 远程传输前必须先白名单化 test_cmd）
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def arch_optimize_regression_guard(
    action: Annotated[Literal["record", "compare", "evoscore"], Field(description="Subcommand to execute")],
    target: Annotated[Optional[str], Field(description="Working directory for 'record' (test command runs here)")] = None,
    baseline: Annotated[Optional[str], Field(description="Baseline JSON file for 'compare'")] = None,
    current: Annotated[Optional[str], Field(description="Current JSON file for 'compare'")] = None,
    history: Annotated[Optional[str], Field(description="History JSON file for 'evoscore'")] = None,
    gamma: Annotated[float, Field(description="Discount factor for 'evoscore'", gt=0)] = 1.5,
    test_cmd: Annotated[Optional[str], Field(description="Test command for 'record' (auto-detected if omitted)")] = None,
    output: Annotated[Optional[str], Field(description="Output JSON file path for 'record'")] = None,
) -> str:
    """Run tests, compare before/after results, and track evolution (Stage 5).

    Three actions are supported:

    * ``record``   - Run a test suite and save results to ``output``.
      Requires ``output``; optionally ``target`` (cwd) and ``test_cmd``.
      Returns the recorded test results JSON.
    * ``compare``  - Diff a ``baseline`` against a ``current`` results file.
      Requires ``baseline`` and ``current``. Returns regressions,
      zero-regression rate, and gate status. A failed gate still returns
      valid JSON (exit code 1 is treated as a result, not an error).
    * ``evoscore`` - Compute the EvoScore from a ``history`` file.
      Requires ``history``; optionally ``gamma`` (default 1.5).

    Args:
        action: One of "record", "compare", "evoscore".
        target: Working directory for ``record`` (defaults to current dir).
        baseline: Baseline JSON file path for ``compare``.
        current: Current JSON file path for ``compare``.
        history: History JSON file path for ``evoscore``.
        gamma: Discount factor for ``evoscore`` (default 1.5, must be > 0).
        test_cmd: Test command for ``record`` (auto-detected if omitted).
        output: Output JSON file path for ``record``.

    Returns:
        JSON string whose contents depend on ``action``: test results
        (record), comparison + gate (compare), or evoscore + trend (evoscore).
    """
    if action == "record":
        return _regression_record(target, test_cmd, output)
    if action == "compare":
        return _regression_compare(baseline, current)
    if action == "evoscore":
        return _regression_evoscore(history, gamma)
    # Unreachable thanks to the Literal type, but kept for defensive safety.
    return json.dumps(
        {"error": f"Unknown action '{action}'. Must be one of: record, compare, evoscore"},
        ensure_ascii=False,
    )


def _regression_record(
    target: Optional[str], test_cmd: Optional[str], output: Optional[str]
) -> str:
    """Handle the ``record`` subcommand.

    ``record`` does not support ``--json``; it writes the structured results
    to the ``--output`` file. We run the subcommand, then read that file back
    so the MCP tool returns structured JSON to the caller.
    """
    if not output:
        return json.dumps(
            {"error": "Parameter 'output' is required for action 'record'"},
            ensure_ascii=False,
        )
    args = ["record", "--output", output, "--cwd", target or "."]
    if test_cmd:
        args += ["--test-cmd", test_cmd]

    script_path = os.path.join(SCRIPTS_DIR, "regression_guard.py")
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=RECORD_TIMEOUT,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {"error": f"Test execution timed out ({RECORD_TIMEOUT}s)"},
            ensure_ascii=False,
        )
    except Exception as e:  # pragma: no cover - defensive
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    if proc.returncode != 0:
        return json.dumps(
            {
                "error": proc.stderr.strip() or proc.stdout.strip() or "Unknown error",
                "returncode": proc.returncode,
            },
            ensure_ascii=False,
        )

    # The structured results were written to the output file; return them.
    try:
        with open(output, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return json.dumps(
            {"error": f"Failed to read output file: {e}", "stdout": proc.stdout.strip()},
            ensure_ascii=False,
        )


def _regression_compare(baseline: Optional[str], current: Optional[str]) -> str:
    """Handle the ``compare`` subcommand.

    ``compare`` prints JSON to stdout *before* returning a non-zero exit code
    when the gate fails, so we return stdout whenever it is non-empty
    regardless of the exit status.
    """
    if not baseline or not current:
        return json.dumps(
            {"error": "Parameters 'baseline' and 'current' are required for action 'compare'"},
            ensure_ascii=False,
        )
    args = ["compare", "--baseline", baseline, "--current", current, "--json"]
    script_path = os.path.join(SCRIPTS_DIR, "regression_guard.py")
    cmd = [sys.executable, script_path] + args
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            encoding="utf-8",
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {"error": f"Script execution timed out ({DEFAULT_TIMEOUT}s)"},
            ensure_ascii=False,
        )
    except Exception as e:  # pragma: no cover - defensive
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    stdout = proc.stdout.strip()
    if stdout:
        # Exit code 1 means the gate failed, not that the call failed.
        return stdout
    return json.dumps(
        {
            "error": proc.stderr.strip() or "Unknown error",
            "returncode": proc.returncode,
        },
        ensure_ascii=False,
    )


def _regression_evoscore(history: Optional[str], gamma: float) -> str:
    """Handle the ``evoscore`` subcommand."""
    if not history:
        return json.dumps(
            {"error": "Parameter 'history' is required for action 'evoscore'"},
            ensure_ascii=False,
        )
    return _run_script(
        "regression_guard.py",
        ["evoscore", "--history", history, "--gamma", str(gamma), "--json"],
    )


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
