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

    _verify_readme_self_scan_claims(data, diag)


def _verify_readme_self_scan_claims(qm, diag):
    """README 自扫段落里的条数与 MI 区间必须能由这两个脚本当场复算。"""
    import re

    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    m = re.search(
        r"`risk_diagnose` from (\d+) Critical \+ (\d+) Warning and "
        r"`quality_metrics` from (\d+) Critical \+ (\d+) Warning",
        readme,
    )
    assert m, "README 的自扫条数句式变了，这条复算断言失效（请同步本检查与 README）"
    claimed = tuple(int(x) for x in m.groups())
    actual = (
        diag["health_score"]["critical"],
        diag["health_score"]["warning"],
        qm["health_score"]["critical"],
        qm["health_score"]["warning"],
    )
    assert claimed == actual, (
        f"README 自扫条数写的是 {claimed}，实测 {actual}——改脚本必须同批改 README"
    )

    rng = re.search(r"below the 15 gate \(([\d.]+)[\u2013-]([\d.]+)\)", readme)
    assert rng, "README 的 MI 区间写法变了，这条复算断言失效"
    scanners = {
        "arch_scan.py",
        "dep_graph.py",
        "quality_metrics.py",
        "risk_diagnose.py",
        "regression_guard.py",
    }
    mis = [
        f["maintainability_index"]
        for f in qm["files"]
        if os.path.basename(f["file"]) in scanners
    ]
    assert len(mis) == 5, f"应复算 5 个扫描器的 MI，实际 {len(mis)} 个"
    lo, hi = float(rng.group(1)), float(rng.group(2))
    assert abs(min(mis) - lo) < 0.05 and abs(max(mis) - hi) < 0.05, (
        f"README 说 MI 区间 {lo}–{hi}，实测 {min(mis)}–{max(mis)}"
    )


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _check_health_density_fields():
    """B 方案：score 保留，另加 scanned_lines + penalty_per_kloc（密度制）。

    实测的两处 score 盲区（也是密度字段存在的理由）：
    - 饱和：risk_diagnose 扫 8 个长函数文件（58 Critical）与 80 个（130 Critical）
      score 都是 0，量不出债务量级；
    - 同分不同债：score 只在同范围前后比较有效。
    密度侧：quality_metrics 纯复制下密度不变（实测 8 份与 80 份同为 79.37，
    每文件 5 Warning / 63 行，比值恒定），可跨项目比较。
    """
    root = tempfile.mkdtemp(prefix="arch-opt-dens-")
    # 每文件一个 63 行的长函数 -> quality_metrics 记 1 个 Warning 热点
    long_fn = (
        "def heavy(a):\n"
        "    v = 0\n" + "".join(f"    v += {i}\n" for i in range(60)) + "    return v\n"
    )

    def build(n):
        target = os.path.join(root, f"n{n}")
        for i in range(n):
            path = os.path.join(target, f"mod{i}", "x.py")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(long_fn)
        return target

    def health(target, script):
        data = run_script(script, "--target", target, "--json")
        return data["health_score"], target

    try:
        h8_rd, t8 = health(build(8), "risk_diagnose.py")
        h80_rd, t80 = health(build(80), "risk_diagnose.py")
        h8_qm, _ = health(os.path.join(root, "n8"), "quality_metrics.py")
        h80_qm, _ = health(os.path.join(root, "n80"), "quality_metrics.py")

        for tag, h in (
            ("rd/8", h8_rd),
            ("rd/80", h80_rd),
            ("qm/8", h8_qm),
            ("qm/80", h80_qm),
        ):
            assert "scanned_lines" in h and "penalty_per_kloc" in h, (
                f"{tag} 缺密度字段：{sorted(h)}"
            )
            # 公式可复算：penalty = 15C+5W+1S，密度 = penalty*1000/lines
            penalty = 15 * h["critical"] + 5 * h["warning"] + 1 * h["suggestion"]
            expected = round(penalty * 1000 / h["scanned_lines"], 2)
            assert h["penalty_per_kloc"] == expected, (
                f"{tag} penalty_per_kloc 不可复算：得到 {h['penalty_per_kloc']}，"
                f"按公式应为 {expected}"
            )

        # 盲区1：score 在 0 处饱和，密度字段恢复量级信息
        assert h8_rd["score"] == h80_rd["score"] == 0, (
            f"饱和前提变了：rd 8/80 分数 {h8_rd['score']}/{h80_rd['score']}"
        )
        assert h8_rd["critical"] != h80_rd["critical"], (
            "两个饱和分数背后的 Critical 数应不同（盲区演示失效）"
        )
        # 盲区2：纯复制下 quality_metrics 密度稳定、score 不稳定
        assert h8_qm["penalty_per_kloc"] == h80_qm["penalty_per_kloc"], (
            f"纯复制下密度应不变：{h8_qm['penalty_per_kloc']} vs "
            f"{h80_qm['penalty_per_kloc']}"
        )
        assert h8_qm["score"] != h80_qm["score"], (
            "纯复制下 score 应因绝对条数累积而变化（这才是它不抗规模的证据）"
        )
        # scanned_lines 口径 = 物理行数（每文件 63 行）
        assert h8_rd["scanned_lines"] == 8 * 63, h8_rd["scanned_lines"]
        assert h80_rd["scanned_lines"] == 80 * 63, h80_rd["scanned_lines"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


CANONICAL_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "__pycache__",
    ".cache",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    "env",
    "testdata",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    "coverage",
}


SCANNER_SCRIPTS = ("arch_scan", "dep_graph", "risk_diagnose", "quality_metrics")


def _module_literal(name, var):
    """从脚本源码取模块级字面量。

    走 AST 而不是 import：import 会被 sys.modules 缓存住，改文件后同进程再读还是旧值，
    这类"表是否一致"的断言就骗得过变异测试。
    """
    import ast

    path = os.path.join(SCRIPTS, f"{name}.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == var for t in node.targets
        ):
            return ast.literal_eval(node.value), src
    raise AssertionError(f"{name}.py 没有模块级 {var} 字面量")


def _check_ignore_dirs_identical():
    """四个扫描器必须用同一张忽略目录表，否则同一个 --target 看到的不同文件集不可比。"""
    for name in SCANNER_SCRIPTS:
        table, src = _module_literal(name, "IGNORE_DIRS")
        assert isinstance(table, set), f"{name} 的 IGNORE_DIRS 不是集合"
        assert table == CANONICAL_IGNORE_DIRS, (
            f"{name} 的忽略目录表与其余脚本不一致：多 {sorted(table - CANONICAL_IGNORE_DIRS)}，"
            f"少 {sorted(CANONICAL_IGNORE_DIRS - table)}"
        )
        assert "not in IGNORE_DIRS" in src, (
            f"{name} 定义了 IGNORE_DIRS 但没有用它过滤目录（目录遍历漏了过滤）"
        )


def _check_ignored_dirs_excluded_from_scan():
    """venv/testdata/env 里的代码不得进任何阶段的文件集，尤其不得污染健康分。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-ignore-")
    long_body = "\n".join(f"    x = x + {i}" for i in range(60))
    src = f"def f(x):\n{long_body}\n    return x\n"
    try:
        for sub in ("pkg", "venv", "testdata", "env"):
            os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
            with open(os.path.join(out_dir, sub, "m.py"), "w", encoding="utf-8") as fh:
                fh.write(src)
        qm = run_script("quality_metrics.py", "--target", out_dir, "--json")
        rd = run_script("risk_diagnose.py", "--target", out_dir, "--json")
        asc = run_script("arch_scan.py", "--target", out_dir, "--json")
        dg = run_script("dep_graph.py", "--target", out_dir, "--json")
        assert qm["files_analyzed"] == 1, (
            f"quality_metrics 只该看到 pkg 的 1 个文件，实际 {qm['files_analyzed']}"
            f"（{[f['file'] for f in qm['files']]}）"
        )
        assert rd["files_analyzed"] == 1, (
            f"risk_diagnose 只该看到 1 个文件，实际 {rd['files_analyzed']}"
        )
        names = [m["name"] for m in asc["modules"]]
        assert "venv" not in names and "testdata" not in names and "env" not in names, (
            f"arch_scan 把被忽略目录报成模块：{names}"
        )
        dg_names = [m["name"] for m in dg["modules"]]
        assert dg_names == ["pkg"], f"dep_graph 的模块集不该含被忽略目录：{dg_names}"
        # 两个计分器用的是不同判据（分数不可比），但同一文件集必须看到同样的行数
        assert (
            qm["health_score"]["scanned_lines"] == rd["health_score"]["scanned_lines"]
        ), (
            f"两个计分器看到的文件集不一致：qm {qm['health_score']['scanned_lines']} 行 vs "
            f"rd {rd['health_score']['scanned_lines']} 行"
        )
        assert all("/pkg/" in f["file"].replace("\\", "/") for f in qm["files"]), (
            f"quality_metrics 的分析集混进了被忽略目录：{[f['file'] for f in qm['files']]}"
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _base(location: str) -> str:
    """发现位置串形如 pkg/main.py:f:1 —— 取文件名的末段用于按文件归类。"""
    return location.split(":")[0].replace("\\", "/").split("/")[-1]


def _check_r2_fanout_fires():
    """R2 的阈值判据必须真能判红，并钉住「按顶层包归一」这一口径。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-r2-")
    wide = (
        "\n".join(f"import dep{i}\n" for i in range(5)) + "\ndef f():\n    return 1\n"
    )
    crit = (
        "\n".join(f"import dep{i}\n" for i in range(8)) + "\ndef f():\n    return 1\n"
    )
    sibling = (
        "\n".join(f"from pkg.sub{i} import X\n" for i in range(8))
        + "\ndef f():\n    return 1\n"
    )
    cases = [
        ("warning.py", wide, "Warning"),
        ("critical.py", crit, "Critical"),
        ("sibling.py", sibling, None),
    ]
    try:
        for name, src, _ in cases:
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                fh.write(src)
        data = run_script("risk_diagnose.py", "--target", out_dir, "--json")
        by_file = {}
        for f in data["findings"]:
            if f["risk"] == "R2":
                by_file[_base(f["location"])] = f["severity"]
        assert by_file.get("warning.py") == "Warning", (
            f"5 个外部依赖应判 Warning，实际 {by_file}"
        )
        assert by_file.get("critical.py") == "Critical", (
            f"8 个外部依赖应判 Critical，实际 {by_file}"
        )
        assert "sibling.py" not in by_file, (
            f"同一顶层包下的 8 条兄弟模块 import 归一后算 1 个依赖，不该报，实际 {by_file}"
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _check_r4_abstraction_fires():
    """R4 的抽象判据必须真能判红，并钉住它只认 ABC/Protocol/Abstract* 命名这一窄口径。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-r4-")
    abc_src = (
        "from abc import ABC, abstractmethod\n"
        "class Store(ABC):\n"
        "    @abstractmethod\n"
        "    def save(self, x):\n"
        "        ...\n"
        "class PgStore(Store):\n"
        "    def save(self, x):\n"
        "        return x\n"
    )
    plain_src = (
        "class Base:\n"
        "    def go(self):\n"
        "        raise NotImplementedError\n"
        "class Only(Base):\n"
        "    def go(self):\n"
        "        return 1\n"
    )
    cc_src = "def f(a):\n" + "".join(
        f"    if a == {i}:\n        return {i}\n" for i in range(25)
    )
    try:
        for name, src in (
            ("abc_one.py", abc_src),
            ("plain_one.py", plain_src),
            ("big_cc.py", cc_src),
        ):
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                fh.write(src)
        data = run_script("risk_diagnose.py", "--target", out_dir, "--json")
        files = {_base(f["location"]) for f in data["findings"] if f["risk"] == "R4"}
        assert "abc_one.py" in files, f"ABC + 唯一实现应判 R4，实际 {sorted(files)}"
        assert "big_cc.py" in files, (
            f"CC=26 (>20) 应判 R4 Critical，实际 {sorted(files)}"
        )
        assert "plain_one.py" not in files, (
            f"R4 目前只认基类名含 ABC/Protocol/Abstract* 的抽象；plain 接口写法是已知盲区，"
            f"若这条开始报了说明判据被放宽，须同步改文档口径。实际 {sorted(files)}"
        )
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _check_language_tables():
    """语言表允许不同，但差异必须恰好是登记过的那一条：dep_graph/risk_diagnose 不认 .java/.kt。"""
    tabs = {}
    for name in SCANNER_SCRIPTS:
        table, _ = _module_literal(name, "LANG_EXTENSIONS")
        tabs[name] = set(table.keys())
    union = set().union(*tabs.values())
    for name, table in tabs.items():
        assert table, f"{name} 的 LANG_EXTENSIONS 为空"
        missing = union - table
        assert missing <= {".java", ".kt"}, (
            f"{name} 的语言表缺未登记的语种扩展：{sorted(missing)}"
        )
    jvm = {n for n, t in tabs.items() if {".java", ".kt"} <= t}
    assert jvm == {"arch_scan", "quality_metrics"}, (
        f".java/.kt 只该被 arch_scan 与 quality_metrics 收录，实际 {sorted(jvm)}"
    )


def _check_r3_magic_literal_aggregation():
    """字面量重复是"一个决策"，必须聚成一条；但量级要能被机读，且判据不许被放宽。"""
    out_dir = tempfile.mkdtemp(prefix="arch-opt-r3mag-")
    os.makedirs(os.path.join(out_dir, "a"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "b"), exist_ok=True)

    def pair(vals):
        for sub in ("a", "b"):
            body = "\n".join(f"V{i} = {v} + {v} + {v}" for i, v in enumerate(vals))
            with open(os.path.join(out_dir, sub, "m.py"), "w", encoding="utf-8") as fh:
                fh.write(body + "\n")

    def magic_findings():
        data = run_script("risk_diagnose.py", "--target", out_dir, "--json")
        return [f for f in data["findings"] if ":magic:" in f["location"]]

    try:
        pair(list(range(10, 61)))  # 51 个不同值 × 3 处 × 2 文件
        lit = magic_findings()
        assert len(lit) == 1, f"51 个不同字面量该聚成 1 条，实际 {len(lit)} 条"
        m = lit[0]["metrics"]
        assert m["distinct_literals"] == 51, m
        assert m["total_uses"] == 306, m
        assert m["files_involved"] == 2, m
        assert [t["uses"] for t in m["top_values"]] == sorted(
            (t["uses"] for t in m["top_values"]), reverse=True
        ), "top_values 必须按出现次数降序"
        assert len(m["top_values"]) == 10, m["top_values"]

        pair([100, 200, 300])  # 3 个值：同样一条，不因量小变成 3 条
        lit = magic_findings()
        assert len(lit) == 1, f"3 个不同字面量也该聚成 1 条，实际 {len(lit)} 条"
        assert lit[0]["metrics"]["distinct_literals"] == 3, lit[0]["metrics"]

        # 判据不放宽：同一文件内重复（不跨文件）不该报
        with open(os.path.join(out_dir, "a", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("X = 100 + 100 + 100\nY = 200 + 200 + 200\n")
        with open(os.path.join(out_dir, "b", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("Z = 1\n")
        assert magic_findings() == [], "跨文件条件不满足时不该报"

        # 每文件只出现 1 次、共 2 处（<3）也不该报
        for sub in ("a", "b"):
            with open(os.path.join(out_dir, sub, "m.py"), "w", encoding="utf-8") as fh:
                fh.write("Q = 7\nR = 7\n")
        assert magic_findings() == [], "总次数 <3 时不该报"

        # 门槛是"同一个值出现 ≥3 次"：只出现 2 次（哪怕跨 2 文件）不该报
        with open(os.path.join(out_dir, "a", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("A = 1234\n")
        with open(os.path.join(out_dir, "b", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("B = 1234\n")
        assert magic_findings() == [], "同一值只出现 2 次时不该报（门槛 ≥3 次）"

        # 两个值各出现 2 次、合计 4 次——仍不该报（门槛按单值计）
        with open(os.path.join(out_dir, "a", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("A = 5000\nA2 = 5000\n")
        with open(os.path.join(out_dir, "b", "m.py"), "w", encoding="utf-8") as fh:
            fh.write("B = 6000\nB2 = 6000\n")
        assert magic_findings() == [], "门槛按单值出现次数计，不该被跨值合计凑出来"

        # 报出来的 top_values 里不许出现 <3 次的值
        pair([100, 200, 300, 400, 500])
        lit = magic_findings()
        assert lit, "5 个值各 3 次跨 2 文件必须报"
        assert all(v["uses"] >= 3 for v in lit[0]["metrics"]["top_values"]), (
            f"报告里不该出现 <3 次的值：{lit[0]['metrics']['top_values']}"
        )
        assert lit[0]["metrics"]["total_uses"] == 30, lit[0]["metrics"]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _check_r5_cycle_fires():
    """R5 的文件级环判据必须有 firing fixture，且相对导入的包内环也要能报。"""
    root = tempfile.mkdtemp(prefix="arch-opt-cyc-")
    try:
        # 绝对导入两文件环
        os.makedirs(os.path.join(root, "abs"), exist_ok=True)
        with open(os.path.join(root, "abs", "x.py"), "w", encoding="utf-8") as fh:
            fh.write("from y import b\n\n\ndef a():\n    return b\n")
        with open(os.path.join(root, "abs", "y.py"), "w", encoding="utf-8") as fh:
            fh.write("from x import a\n\n\ndef b():\n    return a\n")
        data = run_script(
            "risk_diagnose.py", "--target", root, "--risk", "R5", "--json"
        )
        cyc = [f for f in data["findings"] if "循环依赖" in f["symptom"]]
        assert len(cyc) == 1, (
            f"两文件绝对导入环该报 1 条，实际 {len(cyc)}: {[c['symptom'] for c in cyc]}"
        )
        assert cyc[0]["severity"] == "Critical", cyc[0]["severity"]
        assert cyc[0]["symptom"].count("->") >= 2, cyc[0]["symptom"]

        # 三文件链式环 A -> B -> C -> A
        chain = tempfile.mkdtemp(prefix="arch-opt-cyc3-")
        try:
            for name, other in (("m1", "m2"), ("m2", "m3"), ("m3", "m1")):
                with open(
                    os.path.join(chain, f"{name}.py"), "w", encoding="utf-8"
                ) as fh:
                    fh.write(f"from {other} import z\n\n\ndef f():\n    return z\n")
            d3 = run_script(
                "risk_diagnose.py", "--target", chain, "--risk", "R5", "--json"
            )
            c3 = [f for f in d3["findings"] if "循环依赖" in f["symptom"]]
            assert len(c3) == 1, f"三文件环该报 1 条（去重后），实际 {len(c3)}"
            assert c3[0]["symptom"].count("->") == 3, c3[0]["symptom"]
        finally:
            shutil.rmtree(chain, ignore_errors=True)

        # 相对导入指向"嵌套包里的模块"：from .nested import b -> pk/nested/b.py
        deep = tempfile.mkdtemp(prefix="arch-opt-cycdeep-")
        try:
            nd = os.path.join(deep, "pk", "nested")
            os.makedirs(nd, exist_ok=True)
            for d in (os.path.join(deep, "pk"), nd):
                with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as fh:
                    fh.write("")
            with open(os.path.join(nd, "b.py"), "w", encoding="utf-8") as fh:
                fh.write("from pk.top import t\n\n\ndef B():\n    return t\n")
            with open(os.path.join(deep, "pk", "top.py"), "w", encoding="utf-8") as fh:
                fh.write("from .nested import b\n\n\ndef t():\n    return b.B\n")
            dd = run_script(
                "risk_diagnose.py", "--target", deep, "--risk", "R5", "--json"
            )
            cd = [f for f in dd["findings"] if "循环依赖" in f["symptom"]]
            assert len(cd) == 1, (
                "`from .nested import b` 该解析到 pk/nested/b.py 并组成环，实际 "
                f"{len(cd)}: {[x['symptom'] for x in cd]}"
            )
        finally:
            shutil.rmtree(deep, ignore_errors=True)

        # 相对导入只许落在自己包里：本包没有 helper.py，隔壁包有同名文件时不得按
        # basename 乱撞（宽松匹配会凭空造出一条环）
        amb = tempfile.mkdtemp(prefix="arch-opt-cycamb-")
        try:
            for pkgname in ("pk1", "pk2"):
                p_dir = os.path.join(amb, pkgname)
                os.makedirs(p_dir, exist_ok=True)
                with open(
                    os.path.join(p_dir, "__init__.py"), "w", encoding="utf-8"
                ) as fh:
                    fh.write("")
            with open(os.path.join(amb, "pk1", "a.py"), "w", encoding="utf-8") as fh:
                fh.write("from . import helper\n\n\ndef a():\n    return helper\n")
            with open(
                os.path.join(amb, "pk2", "helper.py"), "w", encoding="utf-8"
            ) as fh:
                fh.write("from pk1.a import a\n\n\nhelper = 1\n")
            da = run_script(
                "risk_diagnose.py", "--target", amb, "--risk", "R5", "--json"
            )
            ca = [f for f in da["findings"] if "循环依赖" in f["symptom"]]
            assert not ca, (
                "pk1 内不存在 helper，相对导入不该撞到 pk2/helper.py 造出环："
                f"{[x['symptom'] for x in ca]}"
            )
        finally:
            shutil.rmtree(amb, ignore_errors=True)

        # 相对导入指到"子包"上：from . import sub -> pk/sub/__init__.py
        subp = tempfile.mkdtemp(prefix="arch-opt-cycsub-")
        try:
            sub_dir = os.path.join(subp, "pk", "sub")
            os.makedirs(sub_dir, exist_ok=True)
            with open(
                os.path.join(subp, "pk", "__init__.py"), "w", encoding="utf-8"
            ) as fh:
                fh.write("")
            with open(
                os.path.join(sub_dir, "__init__.py"), "w", encoding="utf-8"
            ) as fh:
                fh.write("from pk.here import h\n")
            with open(os.path.join(subp, "pk", "here.py"), "w", encoding="utf-8") as fh:
                fh.write("from . import sub\n\n\ndef h():\n    return sub\n")
            ds = run_script(
                "risk_diagnose.py", "--target", subp, "--risk", "R5", "--json"
            )
            cs = [f for f in ds["findings"] if "循环依赖" in f["symptom"]]
            assert len(cs) == 1, (
                "`from . import sub` 指到子包目录（pk/sub/__init__.py）时该建边成环，"
                f"实际 {len(cs)}: {[x['symptom'] for x in cs]}"
            )
        finally:
            shutil.rmtree(subp, ignore_errors=True)

        # 跨一级的相对导入：pkg/sub1/a.py 里 `from ..b import z` 该指到 pkg/b.py
        # （故意在仓库根再放一个 b.py：让"按 basename 兜底"的解析变成二义而失效，
        #  于是这条 fixture 只在层级算对时才成立）
        up = tempfile.mkdtemp(prefix="arch-opt-cycup-")
        try:
            s1 = os.path.join(up, "pkg", "sub1")
            os.makedirs(s1, exist_ok=True)
            with open(os.path.join(s1, "a.py"), "w", encoding="utf-8") as fh:
                fh.write("from ..b import z\n\n\ndef a():\n    return z\n")
            with open(os.path.join(up, "pkg", "b.py"), "w", encoding="utf-8") as fh:
                fh.write("from pkg.sub1.a import a\n\n\nz = a\n")
            with open(os.path.join(up, "b.py"), "w", encoding="utf-8") as fh:
                fh.write("decoy = 1\n")
            du = run_script(
                "risk_diagnose.py", "--target", up, "--risk", "R5", "--json"
            )
            cu = [f for f in du["findings"] if "循环依赖" in f["symptom"]]
            assert len(cu) == 1, (
                f"`from ..b import z` 该解析到 pkg/b.py 并成环，实际 {len(cu)}: "
                f"{[x['symptom'] for x in cu]}"
            )
        finally:
            shutil.rmtree(up, ignore_errors=True)

        # 相对导入：包内环（改前不建边）
        pkg = tempfile.mkdtemp(prefix="arch-opt-cycpkg-")
        inner = os.path.join(pkg, "pk")
        os.makedirs(inner, exist_ok=True)
        with open(os.path.join(inner, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("")
        with open(os.path.join(inner, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("from . import b\n\n\ndef a():\n    return b.B\n")
        with open(os.path.join(inner, "b.py"), "w", encoding="utf-8") as fh:
            fh.write("from . import a\n\n\ndef B():\n    return a.a\n")
        dr = run_script("risk_diagnose.py", "--target", pkg, "--risk", "R5", "--json")
        cr = [f for f in dr["findings"] if "循环依赖" in f["symptom"]]
        assert len(cr) == 1, (
            f"相对导入的包内环该报 1 条（SKILL.md 已知限制第 2 条），实际 {len(cr)}: "
            f"{[c['symptom'] for c in cr]}"
        )
        assert "pk/a.py" in cr[0]["symptom"] and "pk/b.py" in cr[0]["symptom"], cr[0][
            "symptom"
        ]

        # 反向 pin：无环项目不得因为相对导入被误报成环
        clean = tempfile.mkdtemp(prefix="arch-opt-cycok-")
        cdir = os.path.join(clean, "pk")
        os.makedirs(cdir, exist_ok=True)
        with open(os.path.join(cdir, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write("")
        with open(os.path.join(cdir, "leaf.py"), "w", encoding="utf-8") as fh:
            fh.write("V = 1\n")
        with open(os.path.join(cdir, "top.py"), "w", encoding="utf-8") as fh:
            fh.write("from .leaf import V\n\n\ndef t():\n    return V\n")
        dc = run_script("risk_diagnose.py", "--target", clean, "--risk", "R5", "--json")
        assert not [f for f in dc["findings"] if "循环依赖" in f["symptom"]], (
            "单向的相对导入被误判成环（会制造假 Critical）"
        )
        shutil.rmtree(cdir, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_cross_lang_function_names():
    """Rust/TS 的发现位置串必须是函数名：改前取"第一个非空捕获组"会拿到 pub / export。"""
    root = tempfile.mkdtemp(prefix="arch-opt-name-")
    long_body_rs = "\n".join(f"    let v{i} = 1;" for i in range(60))
    long_body_ts = "\n".join(f"  const v{i} = 1;" for i in range(60))
    try:
        with open(os.path.join(root, "m.rs"), "w", encoding="utf-8") as fh:
            fh.write(
                f"pub fn big_rs(x: i32) -> i32 {{\n{long_body_rs}\n    return x\n}}\n"
            )
        with open(os.path.join(root, "n.rs"), "w", encoding="utf-8") as fh:
            fh.write(
                f"pub async fn fetch_rs(x: i32) -> i32 {{\n{long_body_rs}\n    return x\n}}\n"
            )
        with open(os.path.join(root, "m.ts"), "w", encoding="utf-8") as fh:
            fh.write(
                f"export function bigTs(a: number): number {{\n{long_body_ts}\n  return a;\n}}\n"
            )
        with open(os.path.join(root, "n.ts"), "w", encoding="utf-8") as fh:
            fh.write(
                f"export async function loadTs(a: number): number "
                f"{{\n{long_body_ts}\n  return a;\n}}\n"
            )
        data = run_script("risk_diagnose.py", "--target", root, "--json")
        seen = {}
        for f in data["findings"]:
            loc = f["location"]
            if loc.startswith(("m.rs", "n.rs", "m.ts", "n.ts")):
                seen.setdefault(loc.split(":")[0], set()).add(loc.split(":")[1])
        expected = {
            "m.rs": "big_rs",
            "n.rs": "fetch_rs",
            "m.ts": "bigTs",
            "n.ts": "loadTs",
        }
        for fname, want in expected.items():
            got = seen.get(fname, set())
            assert want in got, (
                f"{fname} 的发现位置该含函数名 {want}，实际 {got or '无发现'}"
            )
            bad = {
                g
                for g in got
                if g in ("pub", "export", "async", "pub ", "export ") or g.endswith(" ")
            }
            assert not bad, f"{fname} 的位置串带上了关键字而不是函数名：{bad}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _check_asymmetric_score_bounds():
    """`non_asymmetric_score` 必须有界、方向正确、且"弄坏一条 = 修好一条的两倍"。

    改前它按 (target-baseline) 归一，没有新增测试时分母塌成 1：实测
    "3 改进 + 1 真回归"得 +1.979（文档承诺 [0,1]，方向还反了）。
    """
    rg = os.path.join(SCRIPTS, "regression_guard.py")
    out_dir = tempfile.mkdtemp(prefix="arch-opt-asym-")

    def record(name, lines):
        path = os.path.join(out_dir, name)
        p = subprocess.run(
            [
                sys.executable,
                rg,
                "record",
                "--output",
                path,
                "--test-cmd",
                _fake_pytest_cmd(lines),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[:200]
        return path

    def score(base_lines, curr_lines, allow_removed=()):
        b = record("b.json", base_lines)
        c = record("c.json", curr_lines)
        args = [
            sys.executable,
            rg,
            "compare",
            "--baseline",
            b,
            "--current",
            c,
            "--json",
        ]
        for nm in allow_removed:
            args += ["--allow-removed", nm]
        p = subprocess.run(args, capture_output=True, timeout=120, check=False)
        return json.loads(p.stdout.decode("utf-8"))

    P = "PASSED"
    try:
        same = score([f"t.py::a {P}"] * 3, [f"t.py::a {P}"] * 3)
        assert same["non_asymmetric_score"] == 0.0, same["non_asymmetric_score"]

        one_gain = score(
            [f"t.py::a {P}", f"t.py::b {P}", f"t.py::c {P}", "t.py::d FAILED"],
            [f"t.py::{n} {P}" for n in "abcd"],
        )
        one_reg = score(
            [f"t.py::{n} {P}" for n in "abc"] + ["t.py::d FAILED"],
            [f"t.py::a {P}", f"t.py::b {P}", "t.py::c FAILED", "t.py::d FAILED"],
        )
        assert 0.3 < one_gain["non_asymmetric_score"] < 0.4, one_gain[
            "non_asymmetric_score"
        ]
        assert -0.7 < one_reg["non_asymmetric_score"] < -0.6, one_reg[
            "non_asymmetric_score"
        ]
        assert (
            abs(
                abs(one_reg["non_asymmetric_score"])
                - 2 * one_gain["non_asymmetric_score"]
            )
            < 1e-3
        ), "非对称比必须是 2:1（弄坏一条 = 修好一条的两倍）"

        # 文档登记过的旧案例：3 改进 + 1 真回归，改前 +1.979
        old_case = score(
            [f"t.py::p{i} {P}" for i in (1, 2, 3)]
            + [f"t.py::f{i} FAILED" for i in (1, 2, 3)],
            [f"t.py::p{i} {P}" for i in (1, 2)]
            + ["t.py::p3 FAILED"]
            + [f"t.py::f{i} {P}" for i in (1, 2, 3)],
        )
        assert -1.0 <= old_case["non_asymmetric_score"] <= 0.0, (
            f"3 改进 + 1 真回归不得是正分（旧实现给 +1.979），实际 "
            f"{old_case['non_asymmetric_score']}"
        )
        assert old_case["gate_passed"] is False

        vanish = score(
            [f"t.py::{n} {P}" for n in "abcd"],
            [f"t.py::{n} {P}" for n in "abc"],
        )
        assert vanish["non_asymmetric_score"] == -0.5, vanish["non_asymmetric_score"]

        # 有界：再大的改进/再狠的回归都出不了 [-1, 1]
        huge_gain = score(["t.py::a " + P], [f"t.py::{n} {P}" for n in "abcde"])
        huge_reg = score(
            [f"t.py::{n} {P}" for n in "abc"], [f"t.py::{n} FAILED" for n in "abc"]
        )
        assert huge_gain["non_asymmetric_score"] == 1.0, huge_gain[
            "non_asymmetric_score"
        ]
        assert huge_reg["non_asymmetric_score"] == -1.0, huge_reg[
            "non_asymmetric_score"
        ]
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _check_design_review_contract():
    """设计评审层必须存在、七类齐全、五段契约齐全，且没有孤儿参考文档。"""
    ref_dir = os.path.join(ROOT, "references")
    design_path = os.path.join(ref_dir, "design-review.md")
    assert os.path.exists(design_path), (
        "references/design-review.md 缺失（阶段零的定义来源）"
    )

    with open(design_path, encoding="utf-8") as fh:
        text = fh.read()

    seven = (
        "### 1. 变化边界画错",
        "### 2. 耦合的方向与强度",
        "### 3. 抽象的层次与位置",
        "### 4. 不变量归属",
        "### 5. 演化能力与可逆性",
        "### 6. 概念到代码的映射保真（统一语言）",
        "### 7. 一致性与单一事实源",
    )
    missing = [c for c in seven if c not in text]
    assert not missing, f"design-review.md 七类设计问题缺标题 {missing}"

    contract = (
        "1. **决策是什么**",
        "2. **代价与收益**",
        "3. **我赌它错的依据**",
        "4. **若 X 变更发生会怎样**",
        "5. **为什么脚本看不到它**",
    )
    missing = [c for c in contract if c not in text]
    assert not missing, f"design-review.md 五段式发现契约缺项 {missing}"

    with open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8") as fh:
        skill = fh.read()

    for name in sorted(os.listdir(ref_dir)):
        assert name in skill, f"references/{name} 未被 SKILL.md 索引（按需加载会失效）"

    assert "### 阶段零：设计判断" in skill, "SKILL.md 缺少阶段零：设计判断章节"
    assert skill.count("线索生成器") >= 2, "SKILL.md 未把 R1-R6/健康分定位为线索生成器"
    assert "零条发现" in skill, "SKILL.md 未声明『最重的设计问题往往零条发现』"


def _check_all_assertions_wired():
    """每个 _check_* 都必须被 test_smoke 调用——写了但没接线的断言等于不存在。"""
    import re

    with open(os.path.abspath(__file__), encoding="utf-8") as fh:
        src = fh.read()
    defined = set(re.findall(r"^def (_check_\w+)", src, re.M))
    wired = set(re.findall(r"^        (_check_\w+)\(", src, re.M))
    orphan = sorted(defined - wired)
    assert not orphan, f"以下检查已定义但没接进 test_smoke()，不会运行：{orphan}"
    ghost = sorted(wired - defined)
    assert not ghost, f"test_smoke() 调用了不存在的检查：{ghost}"


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
        _check_r5_cycle_fires()
        _check_cross_lang_function_names()
        _check_cc_counts_boolean_operators()
        _check_health_density_fields()
        _check_r6_anemic_detector()
        _check_cli_surface_matches_docs()
        _check_self_scan_claims()
        _check_ignore_dirs_identical()
        _check_language_tables()
        _check_ignored_dirs_excluded_from_scan()
        _check_r2_fanout_fires()
        _check_r4_abstraction_fires()
        _check_r3_magic_literal_aggregation()
        _check_asymmetric_score_bounds()
        _check_design_review_contract()
        _check_all_assertions_wired()
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
