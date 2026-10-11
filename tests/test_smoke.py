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
    assert ("pkg_a", "pkg_b") in edges, (
        f"expected pkg_a->pkg_b edge, got {sorted(edges)}"
    )


def _check_stage2_3(sample):
    diag = run_script("risk_diagnose.py", "--target", sample, "--json")
    for key in ("findings", "findings_by_risk", "health_score", "risks_scanned"):
        assert key in diag, f"risk_diagnose missing key: {key}"
    assert set(diag["risks_scanned"]) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert diag == run_script("risk_diagnose.py", "--target", sample, "--json"), (
        "risk_diagnose should be deterministic"
    )

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
            [
                sys.executable,
                os.path.join(SCRIPTS, "regression_guard.py"),
                "record",
                "--output",
                out_a,
                "--test-cmd",
                fake_test,
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        # record 失败必须让测试失败，不允许静默跳过（否则阶段五永远不被验证）
        assert p.returncode == 0 and os.path.exists(out_a), (
            f"record failed: rc={p.returncode}, "
            f"stderr={p.stderr.decode('utf-8', 'replace')[:300]!r}"
        )
        cmp_p = subprocess.run(
            [
                sys.executable,
                os.path.join(SCRIPTS, "regression_guard.py"),
                "compare",
                "--baseline",
                out_a,
                "--current",
                out_a,
                "--json",
            ],
            capture_output=True,
            timeout=120,
            check=False,
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
        for out, lines in (
            (base, ["t.py::test_a PASSED", "t.py::test_b PASSED"]),
            (cur, ["t.py::test_a FAILED", "t.py::test_b PASSED"]),
        ):
            p = subprocess.run(
                [
                    sys.executable,
                    rg,
                    "record",
                    "--output",
                    out,
                    "--test-cmd",
                    _fake_pytest_cmd(lines),
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[:300]
        cmp_p = subprocess.run(
            [
                sys.executable,
                rg,
                "compare",
                "--baseline",
                base,
                "--current",
                cur,
                "--json",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        result = json.loads(cmp_p.stdout.decode("utf-8"))
        regressed = {r["test"] for r in result["regressions"]}
        assert "t.py::test_a" in regressed, (
            f"真实回归未被判出（gate_passed={result['gate_passed']}）"
        )
        assert result["gate_passed"] is False, "有回归时 gate_passed 必须为 False"
        assert cmp_p.returncode == 1, (
            f"有回归时 compare 退出码必须为 1，实际 {cmp_p.returncode}"
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _check_self_scan_claims():
    """README 的 Self-Scan 段落断言了可复算的事实，代码一变就判红去更新它。"""
    data = run_script(
        "quality_metrics.py",
        "--target",
        os.path.join(ROOT, "scripts"),
        "--json",
    )
    names = [os.path.basename(f["file"]) for f in data["files"]]
    below = [f["file"] for f in data["files"] if f["maintainability_index"] < 15]
    clearing = [
        os.path.basename(f["file"])
        for f in data["files"]
        if f["maintainability_index"] >= 15
    ]
    assert clearing == ["__init__.py"], (
        f"README 说 scripts/ 下只有 __init__.py 能过 MI≥15，实际过线的是 {clearing}"
    )
    assert len(below) == 5, (
        f"README 说五个扫描器全部低于 15，实际 {len(below)} 个低于 15（扫描了 {names}）"
    )

    diag = run_script(
        "risk_diagnose.py", "--target", os.path.join(ROOT, "scripts"), "--json"
    )
    assert diag["health_score"]["score"] == 0, (
        "README 说两个计分器在这个目录上都给 0 分"
    )
    assert diag["health_score"]["critical"] > 0, "README 说 risk_diagnose 侧有 Critical"


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _check_r6_anemic_detector():
    """R6 贫血判据：访问器-only 判 Warning，纯字段判 Suggestion，有行为/DTO/Service 不报。

    改前这个判据是逻辑不可达的：`behavioral` 不排除 property 装饰的方法，所以
    "有 property ⇒ behavioral 非空 ⇒ 条件永不成立"，实测四个用例全部 0 发现。
    """
    root = tempfile.mkdtemp(prefix="arch-opt-r6-")
    cases = {
        # 访问器-only -> Warning
        "accessor_only/domain/customer.py": (
            "class Customer:\n"
            "    def __init__(self, name):\n"
            "        self._name = name\n"
            "\n"
            "    @property\n"
            "    def name(self):\n"
            "        return self._name\n"
            "\n"
            "    @name.setter\n"
            "    def name(self, v):\n"
            "        self._name = v\n",
            "Warning",
        ),
        # get_/set_ 风格 -> Warning
        "getset_style/domain/account.py": (
            "class Account:\n"
            "    def __init__(self, bal):\n"
            "        self._bal = bal\n"
            "\n"
            "    def get_balance(self):\n"
            "        return self._bal\n"
            "\n"
            "    def set_balance(self, v):\n"
            "        self._bal = v\n",
            "Warning",
        ),
        # 纯字段 -> Suggestion（提示，不断言）
        "pure_fields/domain/order.py": (
            "from dataclasses import dataclass\n"
            "\n"
            "\n"
            "@dataclass\n"
            "class Order:\n"
            "    customer_id: str\n"
            "    total_cents: int\n",
            "Suggestion",
        ),
        # 有行为 -> 不报
        "behavioral/domain/invoice.py": (
            "class Invoice:\n"
            "    def __init__(self, total):\n"
            "        self.total = total\n"
            "\n"
            "    def apply_discount(self, pct):\n"
            "        return int(self.total * (100 - pct) / 100)\n",
            "-",
        ),
        # DTO 豁免 -> 不报
        "dto/api/order_dto.py": (
            "class OrderDTO:\n"
            "    def __init__(self, **kw):\n"
            "        self.__dict__.update(kw)\n"
            "\n"
            "    @property\n"
            "    def id(self):\n"
            "        return self.__dict__.get('id')\n",
            "-",
        ),
        # *Service 豁免 -> 不报
        "service/domain/svc.py": (
            "class OrderService:\n"
            "    def place(self, order):\n"
            "        return order\n"
            "\n"
            "    def cancel(self, order):\n"
            "        return None\n",
            "-",
        ),
    }
    try:
        for rel, (src, _expected) in cases.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
        for rel, (_, expected) in cases.items():
            data = run_script(
                "risk_diagnose.py",
                "--target",
                os.path.join(root, rel.split("/")[0]),
                "--risk",
                "R6",
                "--json",
            )
            anemic = [
                f
                for f in data["findings"]
                if "访问器" in f["symptom"] or "只有字段" in f["symptom"]
            ]
            got = anemic[0]["severity"] if anemic else "-"
            assert got == expected, (
                f"{rel}: 期望 {expected}，实际 {got}"
                f"（症状 {anemic[0]['symptom'][:50] if anemic else '无'}）"
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_cc_counts_boolean_operators():
    """非 Python 的 CC 必须数上 &&/||/?/=> —— 把它们塞进 \\b 组里等于永远匹配不到。

    改前实测：if + 7 个 && 真值 9 被算成 2、2 if + 3 || 真值 6 被算成 3、
    三元 ? 真值 2 被算成 1、Rust match 2 臂真值 3 被算成 2、TS && 真值 4 被算成 2。
    口径说明：match/switch 本体也计一次（与仓内 C switch+case 口径一致，
    实测 Rust match 2 臂与 C switch+2 case 都是 4）。
    """
    root = tempfile.mkdtemp(prefix="arch-opt-cc-")
    cases = [
        (
            "a.c",
            "int f(int v0,int v1,int v2,int v3,int v4,int v5,int v6,int v7){\n"
            "    if (" + " && ".join(f"v{i}" for i in range(8)) + ") { return 1; }\n"
            "    return 0;\n}\n",
            9,
            "C: if + 7 个 &&",
        ),
        (
            "b.c",
            "int g(int v0,int v1,int v2,int v3){\n"
            "    if (v0) { return 1; }\n    if ("
            + " || ".join(f"v{i}" for i in range(4))
            + ") { return 2; }\n    return 0;\n}\n",
            6,
            "C: 2 if + 3 ||",
        ),
        ("c.c", "int h(int a){\n    return a > 0 ? 1 : 0;\n}\n", 2, "C: 三元 ?"),
        (
            "d.rs",
            "fn f(y: i32) -> i32 {\n    match y {\n        1 => 2,\n        _ => 0,\n    }\n}\n",
            4,
            "Rust: match 2 臂（本体也计，与 C switch 同口径）",
        ),
        (
            "e.ts",
            "export function k(a: boolean, b: boolean, c: boolean): number {\n"
            "    if (a && b && c) { return 1; }\n    return 0;\n}\n",
            4,
            "TS: if + 2 个 &&",
        ),
        # 反向：可选参数的 ? 不该被算成决策
        (
            "f.ts",
            "export function t(x?: number, y?: string): void {\n    return;\n}\n",
            1,
            "TS: 可选参数 ? 不计决策",
        ),
        (
            "g.go",
            "func q(a int, b int) int {\n    if a > 0 && b > 0 {\n        return 1\n    }\n"
            "    return 0\n}\n",
            3,
            "Go: if + 1 &&",
        ),
    ]
    try:
        wrong = []
        for fname, code, expected, label in cases:
            path = os.path.join(root, fname)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            data = run_script("quality_metrics.py", "--file", path, "--json")
            got = data["files"][0]["cyclomatic_complexity"]["functions"][0]["cc"]
            if got != expected:
                wrong.append(f"{label}: 期望 CC={expected} 实际={got}")
        assert not wrong, "CC 计数偏差:\n  " + "\n  ".join(wrong)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_r5_infra_word_boundary():
    """R5 基础设施匹配必须是词边界：裸子串会把 costs/post/host/netlog 判成 Critical。"""
    root = tempfile.mkdtemp(prefix="arch-opt-r5-")
    # (标签, 文件名, 代码, 是否应命中"直接依赖基础设施")
    cases = [
        ("database", "a.py", "import database", True),
        ("redis", "a.py", "import redis", True),
        ("sqlalchemy", "a.py", "import sqlalchemy", True),
        ("my_db(snake_case)", "a.py", "import my_db", True),
        ("net/http(go)", "a.go", 'import (\n"net/http"\n)', True),
        ("costs", "a.py", "import costs", False),
        ("post", "a.py", "import post", False),
        ("host", "a.py", "import host", False),
        ("netlog", "a.py", "import netlog", False),
    ]
    try:
        wrong = []
        for tag, fname, code, should in cases:
            shutil.rmtree(root, ignore_errors=True)
            path = os.path.join(root, "domain", fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code + "\n\n\ndef go(q):\n    return q\n")
            data = run_script(
                "risk_diagnose.py", "--target", root, "--risk", "R5", "--json"
            )
            hit = any("基础设施" in f["symptom"] for f in data["findings"])
            if hit != should:
                wrong.append(f"{tag}: 期望命中={should} 实际={hit}")
        assert not wrong, "R5 infra 匹配偏差:\n  " + "\n  ".join(wrong)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_r3_cross_context_duplication():
    """R3 跨上下文重复：跨目录要报 Warning（改前 0 条被豁免掉），同目录保持 Critical。"""
    root = tempfile.mkdtemp(prefix="arch-opt-r3-")
    body = "\n".join(f"    step_{i} = base * {i} + {i}" for i in range(28))
    code = (
        "def compute_price(base, qty, rate, tax, discount, fee):\n"
        + body
        + "\n    return base\n"
    )
    try:
        for d in ("billing", "shipping", "reporting"):
            path = os.path.join(root, d, "pricing.py")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        for i in range(3):
            path = os.path.join(root, "same", f"pricing{i}.py")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)

        data = run_script(
            "risk_diagnose.py", "--target", root, "--risk", "R3", "--json"
        )
        blocks = [f for f in data["findings"] if "Jaccard" in f["symptom"]]
        cross = [f for f in blocks if "跨上下文" in f["symptom"]]
        same = [f for f in blocks if "跨上下文" not in f["symptom"]]

        assert cross, "跨目录的逐字节重复必须报出（改前被上下文豁免跳过，实测 0 条）"
        assert all(f["severity"] == "Warning" for f in cross), (
            f"跨上下文应降为 Warning，实际 {sorted({f['severity'] for f in cross})}"
        )
        assert same and all(f["severity"] == "Critical" for f in same), (
            f"同目录重复应保持 Critical，实际 {sorted({f['severity'] for f in same}) or '无'}"
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_gate_blocks_vanish():
    """P0：通过过的测试消失/改名/清空，必须判红；放行通道必须可用。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-vanish-")
    base = os.path.join(out_dir, "baseline.json")
    cur = os.path.join(out_dir, "current.json")
    allow = os.path.join(out_dir, "allow.txt")
    rg = os.path.join(SCRIPTS, "regression_guard.py")
    try:
        for out, lines in (
            (base, ["t.py::a PASSED", "t.py::b PASSED", "t.py::c FAILED"]),
            # 基线里的 c 是失败、a/b 是通过：删 a 必须拦，删 c 不该拦
            (cur, ["t.py::b PASSED", "t.py::c FAILED"]),
        ):
            p = subprocess.run(
                [
                    sys.executable,
                    rg,
                    "record",
                    "--output",
                    out,
                    "--test-cmd",
                    _fake_pytest_cmd(lines),
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[:300]

        def compare(*extra):
            p = subprocess.run(
                [
                    sys.executable,
                    rg,
                    "compare",
                    "--baseline",
                    base,
                    "--current",
                    cur,
                    "--json",
                    *extra,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            return p.returncode, json.loads(p.stdout.decode("utf-8"))

        rc, r = compare()
        assert r["gate_passed"] is False, "通过过的测试消失却放行（硬门被绕过）"
        assert rc == 1, f"有测试消失时退出码必须为 1，实际 {rc}"
        assert r["unexplained_removed_pass"] == ["t.py::a"], r[
            "unexplained_removed_pass"
        ]
        assert any(f["issue"] == "TEST_REMOVED" for f in r["findings"])

        rc, r = compare("--allow-removed", "t.py::a")
        assert r["gate_passed"] is True and rc == 0, "显式放行应当通过"
        assert r["unexplained_removed_pass"] == []

        # 同一放行也可以用文件形式（每行一个名字，# 注释）
        with open(allow, "w", encoding="utf-8") as f:
            f.write("# 有意删除的用例\nt.py::a\n")
        rc, r = compare("--allow-removed-file", allow)
        assert r["gate_passed"] is True and rc == 0, "--allow-removed-file 应当等效"

        # 改名 = 全部消失，必须同样拦住
        renamed = os.path.join(out_dir, "renamed.json")
        with open(renamed, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "command": "fake",
                    "results": {
                        f"renamed_{k}": v
                        for k, v in _load_json(base)["results"].items()
                    },
                },
                f,
            )
        p = subprocess.run(
            [
                sys.executable,
                rg,
                "compare",
                "--baseline",
                base,
                "--current",
                renamed,
                "--json",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        r = json.loads(p.stdout.decode("utf-8"))
        assert r["gate_passed"] is False and p.returncode == 1, "改名绕过未被拦住"

        # 清空整个套件：必须拦住
        empty = os.path.join(out_dir, "empty.json")
        with open(empty, "w", encoding="utf-8") as f:
            json.dump({"command": "fake", "results": {}}, f)
        p = subprocess.run(
            [
                sys.executable,
                rg,
                "compare",
                "--baseline",
                base,
                "--current",
                empty,
                "--json",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        r = json.loads(p.stdout.decode("utf-8"))
        assert r["gate_passed"] is False and p.returncode == 1, "清空套件未被拦住"
        assert r["zero_regression_rate"] == 100.0, (
            "零退化率仍是 100%（这正是要修的口径）"
        )

        # 删掉的是失败测试：不拦（这是合法的清理）
        dropfail = os.path.join(out_dir, "dropfail.json")
        with open(dropfail, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "command": "fake",
                    "results": {
                        k: v
                        for k, v in _load_json(base)["results"].items()
                        if k != "t.py::c"
                    },
                },
                f,
            )
        p = subprocess.run(
            [
                sys.executable,
                rg,
                "compare",
                "--baseline",
                base,
                "--current",
                dropfail,
                "--json",
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        r = json.loads(p.stdout.decode("utf-8"))
        assert r["gate_passed"] is True and p.returncode == 0, (
            "删除一个失败的测试不该判红（会被记为 removed_fail）"
        )
        assert r["removed_fail"] == ["t.py::c"], r["removed_fail"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


EXPECTED_FLAGS = {
    "arch_scan.py": {"--target", "--json", "--depth"},
    "dep_graph.py": {"--target", "--json", "--output", "--format", "--max-depth"},
    "risk_diagnose.py": {"--target", "--file", "--json", "--risk", "--min-severity"},
    "quality_metrics.py": {"--target", "--file", "--json", "--min-cc", "--quiet"},
    "regression_guard.py": {
        "--output",
        "--test-cmd",
        "--cwd",
        "--baseline",
        "--current",
        "--allow-removed",
        "--allow-removed-file",
        "--history",
        "--gamma",
        "--json",
    },
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
    return {tok.split("=")[0] for tok in text.split() if tok.startswith("--")} - {
        "--help"
    }


def _check_cli_surface_matches_docs():
    """文档里的参数面必须等于 argparse 的真实参数面。"""
    import re

    for script, expected in EXPECTED_FLAGS.items():
        actual = _help_flags(script)
        for sub in DOC_SUBCOMMANDS.get(script, ()):
            actual |= _help_flags(script, sub) - {"--help"}
        assert actual == expected, (
            f"{script} 参数面漂移：文档口径 {sorted(expected)}，"
            f"实际 {sorted(actual)}，差集 {sorted(actual ^ expected)}"
        )

    known = {s: set(f) for s, f in EXPECTED_FLAGS.items()}
    for name in DOC_PATHS:
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            text = fh.read()
        for ghost in GHOST_SCRIPTS:
            assert ghost not in text, f"{name} 引用了不存在的脚本 {ghost}"
        assert "Python 3.8" not in text and "3.8+" not in text, (
            f"{name} 仍声明未被 CI 覆盖的旧 Python 版本"
        )
        for line in text.split("\n"):
            for script in known:
                if script not in line:
                    continue
                for flag in re.findall(r"--[a-z][a-z-]*", line):
                    assert flag in known[script], (
                        f"{name} 给 {script} 用了它没有的参数 {flag}"
                    )


def test_smoke(tmp_path=None):
    sample = make_sample_project()
    try:
        _check_stage1(sample)
        _check_stage2_3(sample)
        _check_regression_guard()
        _check_regression_is_detected()
        _check_gate_blocks_vanish()
        _check_r3_cross_context_duplication()
        _check_r5_infra_word_boundary()
        _check_cc_counts_boolean_operators()
        _check_r6_anemic_detector()
        _check_cli_surface_matches_docs()
        _check_self_scan_claims()
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
