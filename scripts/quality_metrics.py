#!/usr/bin/env python3
"""arch-optimize: Quality Metrics Calculator

Calculates Maintainability Index (MI), Cyclomatic Complexity (CC),
Halstead Volume (HV), and Health Score for source code files.

Supports: Python, Go, C/C++, Rust, TypeScript/JavaScript
Dependencies: Python 3.8+ stdlib only

Usage:
    python3 quality_metrics.py --target src/ --json
    python3 quality_metrics.py --file main.go
    python3 quality_metrics.py --target . --threshold-critical 15 --threshold-warning 10
"""

import argparse
import ast
import json
import math
import os
import re
import sys
from pathlib import Path

# ── Language detection ──────────────────────────────────────────────

LANG_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rs": "rust",
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
    ".java": "java", ".kt": "kotlin",
}

# ── LOC counter ─────────────────────────────────────────────────────

def count_loc(filepath: str) -> dict:
    """Count physical, logical, and comment lines."""
    physical = 0
    logical = 0
    comments = 0
    blanks = 0
    in_block_comment = False

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                physical += 1
                if not stripped:
                    blanks += 1
                    continue
                if in_block_comment:
                    comments += 1
                    if "*/" in stripped:
                        in_block_comment = False
                    continue
                if stripped.startswith("//") or stripped.startswith("#"):
                    comments += 1
                    continue
                if stripped.startswith("/*"):
                    comments += 1
                    if "*/" not in stripped:
                        in_block_comment = True
                    continue
                logical += 1
    except Exception:
        pass

    return {
        "physical": physical,
        "logical": logical,
        "comments": comments,
        "blanks": blanks,
    }


# ── Cyclomatic Complexity ───────────────────────────────────────────

def cc_python(filepath: str) -> list:
    """Calculate CC for each function in a Python file using ast."""
    results = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read(), filename=filepath)
    except SyntaxError:
        return results
    except Exception:
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = 1
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    cc += 1
                elif isinstance(child, ast.ExceptHandler):
                    cc += 1
                elif isinstance(child, ast.BoolOp):
                    cc += len(child.values) - 1
                elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    cc += 1
                elif isinstance(child, ast.Assert):
                    cc += 1
            results.append({
                "function": node.name,
                "line": node.lineno,
                "cc": cc,
                "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
            })
    return results


# Decision keywords for C-family languages
C_DECISION_RE = re.compile(
    r"\b(if|else\s+if|for|while|case|catch|\?\s|&&|\|\||switch)\b",
    re.MULTILINE,
)

# Decision keywords for Go
GO_DECISION_RE = re.compile(
    r"\b(if|else\s+if|for|switch|case|select|&&|\|\|)\b",
    re.MULTILINE,
)

# Decision keywords for Rust
RUST_DECISION_RE = re.compile(
    r"\b(if|else\s+if|for|while|loop|match|=>|&&|\|\|)\b",
    re.MULTILINE,
)

FUNC_RE = {
    "go": re.compile(r"^func\s+(\w+)", re.MULTILINE),
    "c": re.compile(r"^\w[\w\s\*]*\s+(\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
    "cpp": re.compile(r"^\w[\w\s\*<>:,]*\s+(\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
    "rust": re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+(\w+)", re.MULTILINE),
    "typescript": re.compile(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)|^\s*(\w+)\s*\([^)]*\)\s*[:{]", re.MULTILINE),
    "javascript": re.compile(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)|^\s*(\w+)\s*\([^)]*\)\s*[:{]", re.MULTILINE),
    "java": re.compile(r"^\s*(public|private|protected)?\s*(static)?\s*\w[\w<>\[\]]*\s+(\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
}

DECISION_RE = {
    "go": GO_DECISION_RE,
    "c": C_DECISION_RE,
    "cpp": C_DECISION_RE,
    "rust": RUST_DECISION_RE,
    "typescript": C_DECISION_RE,
    "javascript": C_DECISION_RE,
    "java": C_DECISION_RE,
}


def cc_c_family(filepath: str, lang: str) -> list:
    """Approximate CC for C/C++/Go/Rust/TS/JS/Java using regex."""
    results = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception:
        return results

    func_re = FUNC_RE.get(lang)
    decision_re = DECISION_RE.get(lang)
    if not func_re or not decision_re:
        return results

    lines = source.split("\n")

    for match in func_re.finditer(source):
        func_name = match.group(match.lastindex) if match.groups() else "anonymous"
        start_line = source[:match.start()].count("\n") + 1

        # Find function body extent (simple brace matching)
        brace_count = 0
        end_line = start_line
        started = False
        for i in range(start_line - 1, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    brace_count += 1
                    started = True
                elif ch == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        end_line = i + 1
                        break
            if started and brace_count == 0:
                break

        func_body = "\n".join(lines[start_line - 1:end_line])
        decisions = len(decision_re.findall(func_body))
        cc = 1 + decisions
        results.append({
            "function": func_name,
            "line": start_line,
            "cc": cc,
            "lines": end_line - start_line + 1,
        })
    return results


def calculate_cc(filepath: str, lang: str) -> list:
    """Calculate cyclomatic complexity for all functions in a file."""
    if lang == "python":
        return cc_python(filepath)
    return cc_c_family(filepath, lang)


# ── Halstead Volume (simplified) ────────────────────────────────────

OPERATORS_RE = re.compile(
    r"[+\-*/%=<>!&|^~?:]|"
    r"\+\+|--|->|::|<<|>>|<=|>=|==|!=|&&|\|\||"
    r"\+=|-=|\*=|/=|%=|<<=|>>=|&=|\|=|\^="
)

OPERANDS_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\b|"
    r"\b\d+\.?\d*\b|"
    r'"[^"]*"|'
    r"'[^']*'"
)


def calculate_hv(filepath: str) -> float:
    """Calculate Halstead Volume (simplified estimation)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception:
        return 0.0

    operators = OPERATORS_RE.findall(source)
    operands = OPERANDS_RE.findall(source)

    n1 = len(set(operators))  # distinct operators
    n2 = len(set(operands))   # distinct operands
    N1 = len(operators)       # total operators
    N2 = len(operands)        # total operands

    vocabulary = n1 + n2
    length = N1 + N2

    if vocabulary <= 1:
        return 0.0

    return length * math.log2(vocabulary)


# ── Maintainability Index ───────────────────────────────────────────

def calculate_mi(hv: float, cc_avg: float, loc: int) -> float:
    """
    MI = MAX(0, (171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)) * 100/171)
    """
    if loc <= 1:
        return 100.0
    if hv <= 1:
        hv = 1.0

    mi = (171 - 5.2 * math.log(hv) - 0.23 * cc_avg - 16.2 * math.log(loc)) * 100 / 171
    return max(0.0, mi)


# ── Health Score ────────────────────────────────────────────────────

def calculate_health_score(findings: list) -> dict:
    """
    Health Score = 100 - 15*Critical - 5*Warning - 1*Suggestion
    """
    critical = sum(1 for f in findings if f.get("severity") == "Critical")
    warning = sum(1 for f in findings if f.get("severity") == "Warning")
    suggestion = sum(1 for f in findings if f.get("severity") == "Suggestion")

    score = max(0, 100 - 15 * critical - 5 * warning - 1 * suggestion)

    if score >= 90:
        grade = "优秀"
    elif score >= 70:
        grade = "良好"
    elif score >= 50:
        grade = "需关注"
    else:
        grade = "危险"

    return {
        "score": score,
        "grade": grade,
        "critical": critical,
        "warning": warning,
        "suggestion": suggestion,
    }


# ── Main analysis ───────────────────────────────────────────────────

def analyze_file(filepath: str) -> dict:
    """Analyze a single source file."""
    ext = Path(filepath).suffix.lower()
    lang = LANG_EXTENSIONS.get(ext)
    if not lang:
        return None

    loc_data = count_loc(filepath)
    hv = calculate_hv(filepath)
    cc_data = calculate_cc(filepath, lang)

    cc_values = [c["cc"] for c in cc_data] if cc_data else [1]
    cc_avg = sum(cc_values) / len(cc_values) if cc_values else 1
    cc_max = max(cc_values) if cc_values else 1

    mi = calculate_mi(hv, cc_avg, loc_data["logical"])

    # Identify hotspots
    hotspots = []
    for func in cc_data:
        if func["cc"] > 15:
            hotspots.append({
                "function": func["function"],
                "line": func["line"],
                "cc": func["cc"],
                "lines": func["lines"],
                "severity": "Critical" if func["cc"] > 15 else "Warning",
                "issue": "R1 认知过载" if func["lines"] > 50 else "R4 偶发复杂性",
            })
        elif func["lines"] > 50:
            hotspots.append({
                "function": func["function"],
                "line": func["line"],
                "cc": func["cc"],
                "lines": func["lines"],
                "severity": "Warning",
                "issue": "R1 认知过载 (函数>50行)",
            })

    return {
        "file": filepath,
        "language": lang,
        "loc": loc_data,
        "halstead_volume": round(hv, 2),
        "cyclomatic_complexity": {
            "average": round(cc_avg, 2),
            "max": cc_max,
            "functions": cc_data,
        },
        "maintainability_index": round(mi, 2),
        "mi_grade": "绿色" if mi > 20 else ("黄色" if mi >= 10 else "红色"),
        "hotspots": hotspots,
    }


def analyze_target(target: str) -> dict:
    """Analyze a file or directory."""
    results = []
    if os.path.isfile(target):
        r = analyze_file(target)
        if r:
            results.append(r)
    elif os.path.isdir(target):
        for root, dirs, files in os.walk(target):
            # Skip common ignore dirs
            dirs[:] = [d for d in dirs if d not in {
                ".git", "node_modules", "vendor", "__pycache__",
                ".cache", "dist", "build", "target", ".venv",
            }]
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                ext = Path(fname).suffix.lower()
                if ext in LANG_EXTENSIONS:
                    r = analyze_file(fpath)
                    if r:
                        results.append(r)

    if not results:
        return {"error": "No analyzable source files found", "target": target}

    # Aggregate metrics
    all_hotspots = []
    total_loc = 0
    mi_values = []
    cc_values = []

    for r in results:
        all_hotspots.extend(r["hotspots"])
        total_loc += r["loc"]["logical"]
        mi_values.append(r["maintainability_index"])
        cc_values.append(r["cyclomatic_complexity"]["average"])

    avg_mi = sum(mi_values) / len(mi_values) if mi_values else 0
    avg_cc = sum(cc_values) / len(cc_values) if cc_values else 0

    # Generate findings from hotspots
    findings = []
    for hs in all_hotspots:
        findings.append({
            "severity": hs["severity"],
            "issue": hs["issue"],
            "location": f"{hs['function']}():{hs['line']}",
            "detail": f"CC={hs['cc']}, lines={hs['lines']}",
        })

    health = calculate_health_score(findings)

    return {
        "target": target,
        "files_analyzed": len(results),
        "total_logical_loc": total_loc,
        "average_mi": round(avg_mi, 2),
        "average_cc": round(avg_cc, 2),
        "health_score": health,
        "hotspots": all_hotspots,
        "files": results,
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="arch-optimize: Quality Metrics Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file main.py
  %(prog)s --target src/ --json
  %(prog)s --target . --min-cc 10
        """,
    )
    parser.add_argument("--file", help="Analyze a single file")
    parser.add_argument("--target", help="Analyze a directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--min-cc", type=int, default=0, help="Only show functions with CC >= N")
    parser.add_argument("--quiet", action="store_true", help="Only show summary")

    args = parser.parse_args()

    if not args.file and not args.target:
        parser.print_help()
        sys.exit(1)

    target = args.file or args.target
    result = analyze_target(target)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        # Filter by min-cc
        if args.min_cc > 0 and "files" in result:
            for f in result["files"]:
                f["cyclomatic_complexity"]["functions"] = [
                    func for func in f["cyclomatic_complexity"]["functions"]
                    if func["cc"] >= args.min_cc
                ]
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Human-readable output
        print(f"\n{'='*60}")
        print(f"  arch-optimize Quality Report")
        print(f"{'='*60}")
        print(f"  Target:           {result['target']}")
        print(f"  Files analyzed:   {result['files_analyzed']}")
        print(f"  Total LOC:        {result['total_logical_loc']}")
        print(f"  Average MI:       {result['average_mi']} ({'🟢' if result['average_mi'] > 20 else '🟡' if result['average_mi'] >= 10 else '🔴'})")
        print(f"  Average CC:       {result['average_cc']}")
        hs = result["health_score"]
        print(f"  Health Score:     {hs['score']}/100 ({hs['grade']})")
        print(f"  Critical:         {hs['critical']}")
        print(f"  Warning:          {hs['warning']}")
        print(f"  Suggestion:       {hs['suggestion']}")

        if result["hotspots"] and not args.quiet:
            print(f"\n  {'─'*56}")
            print(f"  Hotspots ({len(result['hotspots'])}):")
            print(f"  {'─'*56}")
            for hs in result["hotspots"][:20]:
                print(f"  [{hs['severity']:9s}] {hs['function']}():{hs['line']}  CC={hs['cc']}  lines={hs['lines']}  {hs['issue']}")
            if len(result["hotspots"]) > 20:
                print(f"  ... and {len(result['hotspots']) - 20} more")

        print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
