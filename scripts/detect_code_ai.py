#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_code_ai.py — 检测代码中的 AI 味模式 (Detect AI-flavored patterns in code)

检测 DEAD-001 ~ DEAD-010 共 10 类 AI 生成代码的典型低质量模式。
Python 3.8+ 标准库零依赖。

支持语言: Python / Go / C / C++ / Rust / TypeScript / JavaScript

用法:
    python3 detect_code_ai.py --target <项目目录> --json
    python3 detect_code_ai.py --file <单文件> --json
    python3 detect_code_ai.py --target ./src --json --output report.json
    python3 detect_code_ai.py --file main.py --min-severity Warning
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set, Tuple

# --------------------------------------------------------------------------- #
# 常量定义
# --------------------------------------------------------------------------- #

SEVERITY_WEIGHT = {
    "Blocker": 25,
    "Critical": 15,
    "Warning": 5,
}

LANG_BY_EXT = {
    ".py": "python",
    ".go": "go",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp",
    ".rs": "rust",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".mjs": "javascript",
}

# DEAD-002 占位符关键词
PLACEHOLDER_TOKENS = [
    "TODO", "FIXME", "XXX", "HACK",
    "NotImplementedError", "NotImplemented",
    "placeholder", "Placeholder", "PLACEHOLDER",
    "stub", "Stub", "STUB",
    "dummy", "Dummy",
    "模拟实现", "内存模拟", "模拟数据", "假数据",
    "后续实现", "后续替换", "暂时实现", "临时实现",
]

# DEAD-005 无意义命名
MEANINGLESS_NAMES = re.compile(
    r"\b("
    r"data[0-9]?|temp[0-9]?|tmp[0-9]?|foo|bar|baz|qux|"
    r"stuff|thing|things|obj[0-9]?|item[0-9]?|var[0-9]?|"
    r"val[0-9]?|misc|something|whatever|asdf"
    r")\b"
)

# DEAD-009 已知幻觉 API 模式（调用不存在的标准库方法）
# (语言, 正则, 说明)
HALLUCINATED_APIS: List[Tuple[str, str, str]] = [
    ("python", r"\.to_iso_string\(", "datetime 没有to_iso_string方法，应为 isoformat()"),
    ("python", r"\.to_isoformat\(", "应为 .isoformat() 而非 to_isoformat()"),
    ("python", r"\.reverse\(\)\s*$", "str 没有reverse方法，应用切片 [::-1]"),
    ("python", r"\.remove_all\(", "list 没有remove_all方法"),
    ("python", r"\.contains\(", "list/dict 没有contains方法，应用 in 操作符"),
    ("python", r"\.size\(\)", "list/dict 没有size()方法，应用 len()"),
    ("python", r"\.length\(\)", "list/dict/str 没有length()方法，应用 len()"),
    ("python", r"\.first\(\)", "list 没有first()方法，应用 lst[0]"),
    ("python", r"\.last\(\)", "list 没有last()方法，应用 lst[-1]"),
    ("python", r"\.push\(", "list 没有push方法，应用 append()"),
    ("python", r"datetime\.now\(\)\.strftime\([^)]*\)\.to_iso", "链式幻觉调用"),
    ("javascript", r"\.last\(\)\b(?!\s*[:(])", "原生数组没有 last()（ES2022前），应用 arr[arr.length-1]"),
    ("javascript", r"\.contains\(", "数组没有contains，应用 includes()"),
    ("typescript", r"\.contains\(", "数组没有contains，应用 includes()"),
    ("go", r"strings\.ContainsAny\([^,]*\)", "检查参数数量，ContainsAny 需要两个参数"),
]

# 明显注释模式（DEAD-004）：注释只是复述代码的显而易见行为
OBVIOUS_COMMENT_PATTERNS = [
    re.compile(r"#\s*(i|j|k|n|count|cnt|num)\s*\+?=\s*1\s*$"),  # # i加1 / i += 1
    re.compile(r"#\s*(循环|返回|输出|打印|初始化|定义|赋值|加一|自增|递增|开始|结束)\s*$"),
    re.compile(r"#\s*return\s*$"),
    re.compile(r"#\s*for\s+loop\s*$", re.I),
    re.compile(r"#\s*if\s+statement\s*$", re.I),
    re.compile(r"#\s*(get|set|create|delete|update)\s*$", re.I),
    re.compile(r"//\s*(循环|返回|输出|打印|初始化|定义|赋值|开始|结束)\s*$"),
    re.compile(r"//\s*for\s+loop\s*$", re.I),
    re.compile(r"//\s*return\s*$"),
]


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    pattern_id: str
    severity: str
    location: str
    symptom: str
    remedy: str


@dataclass
class FileReport:
    path: str
    language: str
    line_count: int = 0
    findings: List[Finding] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def detect_language(path: str) -> Optional[str]:
    ext = os.path.splitext(path)[1].lower()
    return LANG_BY_EXT.get(ext)


def read_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def loc(line: str) -> str:
    """返回去掉首尾空白后的代码内容（用于判断是否空行/纯注释）。"""
    return line.strip()


def is_comment_line(line: str, lang: str) -> bool:
    s = line.strip()
    if lang in ("python",):
        return s.startswith("#")
    if lang in ("c", "cpp", "rust", "go", "typescript", "javascript"):
        return s.startswith("//") or s.startswith("/*") or s.startswith("*")
    return s.startswith("#") or s.startswith("//")


def is_blank(line: str) -> bool:
    return len(line.strip()) == 0


def add(report: FileReport, pid: str, severity: str, line_no: int,
        symptom: str, remedy: str) -> None:
    report.findings.append(Finding(
        pattern_id=pid,
        severity=severity,
        location=f"{report.path}:{line_no}",
        symptom=symptom,
        remedy=remedy,
    ))


def collect_files(target: Optional[str], single_file: Optional[str],
                  exclude_dirs: Set[str]) -> List[str]:
    files: List[str] = []
    if single_file:
        if os.path.isfile(single_file):
            files.append(os.path.abspath(single_file))
        return files
    if not target or not os.path.isdir(target):
        return files
    for root, dirs, fnames in os.walk(target):
        # 原地修改 dirs 以跳过排除目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fn in fnames:
            full = os.path.join(root, fn)
            if detect_language(full):
                files.append(os.path.abspath(full))
    return files


# --------------------------------------------------------------------------- #
# Python AST 辅助
# --------------------------------------------------------------------------- #

class PyUsageCollector(ast.NodeVisitor):
    """收集模块中所有被引用的 Name。"""

    def __init__(self) -> None:
        self.used: Set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        self.used.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # 只收集属性名本身也作为潜在引用（如 a.b 中的 b 不算导入引用）
        self.generic_visit(node)


class PyDefCollector(ast.NodeVisitor):
    """收集所有定义的 import 名、函数名、类名、赋值变量名。"""

    def __init__(self) -> None:
        self.imports: List[Tuple[str, int, str]] = []  # (name, lineno, alias_or_module)
        self.funcs: List[Tuple[str, int]] = []
        self.classes: List[Tuple[str, int]] = []
        self.assigns: List[Tuple[str, int]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.imports.append((name, node.lineno, alias.name))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            name = alias.asname or alias.name
            self.imports.append((name, node.lineno, alias.name))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.funcs.append((node.name, node.lineno))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.funcs.append((node.name, node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append((node.name, node.lineno))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                self.assigns.append((tgt.id, node.lineno))
        self.generic_visit(node)


def py_func_body_is_trivial(node: ast.FunctionDef) -> bool:
    """判断函数体是否只有 pass/return None/return {}/return []/return \"\"。"""
    body = node.body
    # 去掉 docstring
    real_body = [n for n in body if not (
        isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), (ast.Str, ast.Constant))
    )]
    if not real_body:
        return True
    if len(real_body) == 1:
        stmt = real_body[0]
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Return):
            v = stmt.value
            if v is None:
                return True
            if isinstance(v, ast.Constant) and v.value is None:
                return True
            if isinstance(v, (ast.Dict, ast.List, ast.Set)):
                # 空 dict/list/set
                if not getattr(v, "keys", None) and not getattr(v, "values", None) \
                        and not getattr(v, "elts", None):
                    return True
            if isinstance(v, ast.Constant) and v.value == "":
                return True
    return False


def py_class_only_static_methods(node: ast.ClassDef) -> bool:
    """判断类是否只包含静态方法（过度工程化嫌疑）。"""
    methods = [n for n in node.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not methods or len(methods) < 2:
        return False
    for m in methods:
        is_static = any(isinstance(d, ast.Name) and d.id == "staticmethod"
                        for d in m.decorator_list)
        is_class = any(isinstance(d, ast.Name) and d.id == "classmethod"
                       for d in m.decorator_list)
        if not is_static and not is_class:
            return False
    return True


def py_find_trivial_excepts(tree: ast.AST) -> List[Tuple[int, str]]:
    """查找空 except 或只打印的 except。返回 (lineno, 描述)。"""
    results: List[Tuple[int, str]] = []

    class Visitor(ast.NodeVisitor):
        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            body = node.body
            # 空异常体（只有 pass）
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                results.append((node.lineno, "except 块只有 pass，异常被静默吞掉"))
            # 只有一句 print/log 调用
            elif len(body) == 1 and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Call):
                call = body[0].value
                fname = ""
                if isinstance(call.func, ast.Name):
                    fname = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    fname = call.func.attr
                if fname in ("print", "log", "logging", "logger", "warn", "warning",
                             "debug", "info", "error"):
                    results.append((node.lineno,
                                    f"except 块只调用 {fname}()，未真正处理异常"))
            self.generic_visit(node)

    Visitor().visit(tree)
    return results


def py_find_repetitive_blocks(tree: ast.AST) -> List[Tuple[int, str]]:
    """查找连续 3+ 个相似的 try 或 if 结构。"""
    results: List[Tuple[int, str]] = []

    class Visitor(ast.NodeVisitor):
        def _scan_sequence(self, body: List[ast.stmt]) -> None:
            seq_try: List[ast.Try] = []
            for stmt in body:
                if isinstance(stmt, ast.Try):
                    seq_try.append(stmt)
                else:
                    if len(seq_try) >= 3:
                        results.append((seq_try[0].lineno,
                                        f"连续 {len(seq_try)} 个 try-except 块，疑似重复模式"))
                    seq_try = []
                self.generic_visit(stmt)
            if len(seq_try) >= 3:
                results.append((seq_try[0].lineno,
                                f"连续 {len(seq_try)} 个 try-except 块，疑似重复模式"))

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._scan_sequence(node.body)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._scan_sequence(node.body)
            self.generic_visit(node)

        def visit_Module(self, node: ast.Module) -> None:
            self._scan_sequence(node.body)

    Visitor().visit(tree)
    return results


# --------------------------------------------------------------------------- #
# 各检测器
# --------------------------------------------------------------------------- #

def detect_dead001_dead_code(report: FileReport, lines: List[str],
                             tree: Optional[ast.AST]) -> None:
    """DEAD-001 死代码：未使用的 import/函数/变量。"""
    lang = report.language
    if lang == "python" and tree is not None:
        defs = PyDefCollector()
        defs.visit(tree)
        usage = PyUsageCollector()
        usage.visit(tree)
        # 未使用的 import
        for name, lineno, origin in defs.imports:
            if name not in usage.used and name != "__future__":
                add(report, "DEAD-001", "Critical", lineno,
                    f"未使用的 import: {origin} (绑定名 {name})",
                    "删除该 import，或如果是刻意保留请加 # noqa 说明")
        # 未使用的顶层函数（排除 __main__ 守卫与 dunder 方法）
        for name, lineno in defs.funcs:
            if name.startswith("_") and name.endswith("_"):
                continue
            if name not in usage.used:
                add(report, "DEAD-001", "Critical", lineno,
                    f"未使用的函数: {name}() 定义后从未被调用",
                    "删除该函数，或确认是否为公开 API 入口")
        return

    # 非Python：正则检测未使用的 import
    used_text = "\n".join(lines)
    if lang in ("c", "cpp"):
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*#include\s*[\"<]([^\">]+)[\">]", line)
            if m:
                header = m.group(1)
                # 以头文件主名作为使用依据
                stem = re.sub(r"\.(h|hpp|hh|hxx)$", "", header)
                if stem and not re.search(r"\b" + re.escape(stem) + r"\b", used_text, re.I):
                    # include 本身不算使用，找函数符号太复杂，仅对明显未引用的头文件提示
                    pass  # C/C++ 头文件使用难以静态判定，跳过避免假阳性
    elif lang == "go":
        # Go: import 必须使用，编译器会报错；这里检测单行 import 未使用
        for i, line in enumerate(lines, 1):
            m = re.match(r'\s*"([^"]+)"\s*$', line)
            if m and not line.strip().startswith("//"):
                pkg = m.group(1).split("/")[-1]
                if pkg and not re.search(r"\b" + re.escape(pkg) + r"\.", used_text):
                    add(report, "DEAD-001", "Critical", i,
                        f"未使用的 Go import: {m.group(1)}",
                        "删除该 import（Go 编译器强制要求使用所有 import）")
    elif lang in ("rust",):
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*use\s+([\w:]+)", line)
            if m:
                last = m.group(1).split("::")[-1]
                if last and last != "*" and not re.search(r"\b" + re.escape(last) + r"\b", used_text):
                    add(report, "DEAD-001", "Critical", i,
                        f"未使用的 use: {m.group(1)}",
                        "删除该 use 项（Rust 编译器会警告 unused import）")
    elif lang in ("typescript", "javascript"):
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*import\s+(?:\{([^}]+)\}|\w+)\s+from", line)
            if m:
                names = re.split(r"[,\s]+", m.group(1).strip()) if m.group(1) else []
                for nm in names:
                    nm = nm.strip().split(r"\s+as\s+")[-1].strip()
                    if nm and not re.search(r"\b" + re.escape(nm) + r"\b", used_text):
                        add(report, "DEAD-001", "Critical", i,
                            f"未使用的 import: {nm}",
                            "删除该导入项")


def detect_dead002_placeholders(report: FileReport, lines: List[str]) -> None:
    """DEAD-002 占位符：TODO/FIXME/pass/NotImplemented/模拟/stub 等。"""
    lang = report.language
    for i, line in enumerate(lines, 1):
        s = line.strip()
        # 跳过纯注释行的 TODO 也可报，但区分严重性
        for tok in PLACEHOLDER_TOKENS:
            if tok in line:
                # Python: pass 单独成句才算占位（except:pass 归 DEAD-008）
                if tok == "pass" and lang == "python":
                    if re.match(r"^\s*pass\s*$", line):
                        add(report, "DEAD-002", "Critical", i,
                            "占位符: 函数/块体仅含 pass",
                            "实现真实逻辑，或明确告知用户当前无法实现")
                    continue
                if tok in ("NotImplementedError", "NotImplemented"):
                    add(report, "DEAD-002", "Critical", i,
                        f"占位符: 抛出 {tok}，未实现真实逻辑",
                        "实现真实逻辑，或明确告知用户当前无法实现")
                    continue
                add(report, "DEAD-002", "Critical", i,
                    f"占位符标记: {tok}",
                    "实现真实逻辑，或明确告知用户当前无法实现")


def detect_dead003_fake_impl(report: FileReport, lines: List[str],
                              tree: Optional[ast.AST]) -> None:
    """DEAD-003 假实现：标记词 + 空函数体。"""
    lang = report.language
    marker_words = ["模拟实现", "内存模拟", "模拟数据", "假数据", "后续替换",
                    "后续实现", "暂时实现", "临时实现", "临时方案", "示例实现"]
    # 1) 注释中出现假实现标记词
    for i, line in enumerate(lines, 1):
        for w in marker_words:
            if w in line:
                add(report, "DEAD-003", "Blocker", i,
                    f"假实现标记: 代码中出现 '{w}'",
                    "必须用真实实现替换，禁止用模拟冒充真实系统")
    # 2) Python: 函数体 trivial 且函数名暗示真实功能
    if lang == "python" and tree is not None:
        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if py_func_body_is_trivial(node):
                    # 排除抽象方法/协议方法
                    is_abstract = any(
                        (isinstance(d, ast.Name) and d.id == "abstractmethod")
                        or (isinstance(d, ast.Attribute) and d.attr == "abstractmethod")
                        for d in node.decorator_list
                    )
                    if not is_abstract:
                        add(report, "DEAD-003", "Blocker", node.lineno,
                            f"假实现: 函数 {node.name}() 体为空（pass/return None/空容器）",
                            "实现真实业务逻辑，或标注为抽象方法/接口")
                self.generic_visit(node)
        V().visit(tree)
    # 3) 其他语言：检测空函数体 {} / { return; } / { return None; }
    if lang in ("c", "cpp", "rust", "go", "typescript", "javascript"):
        for i, line in enumerate(lines, 1):
            if re.search(r"\{\s*\}", line):
                # 排除对象字面量和初始化
                if not re.search(r"(=>|return|=|const|let|var)\s*\{\s*\}", line):
                    add(report, "DEAD-003", "Blocker", i,
                        "假实现: 空函数体 {}",
                        "实现真实业务逻辑，不要留空函数体")
            if re.search(r"\{\s*return\s*(None|null|nil|undefined)?\s*;?\s*\}", line):
                add(report, "DEAD-003", "Blocker", i,
                    "假实现: 函数体仅 return None/null",
                    "实现真实业务逻辑")


def detect_dead004_over_comment(report: FileReport, lines: List[str]) -> None:
    """DEAD-004 过度注释：注释/代码比 > 0.5 且注释内容显而易见。"""
    lang = report.language
    comment_lines = 0
    code_lines = 0
    obvious_hits: List[int] = []
    for i, line in enumerate(lines, 1):
        if is_blank(line):
            continue
        if is_comment_line(line, lang):
            comment_lines += 1
            for pat in OBVIOUS_COMMENT_PATTERNS:
                if pat.search(line):
                    obvious_hits.append(i)
                    break
        else:
            code_lines += 1
    if code_lines > 0 and comment_lines / max(code_lines, 1) > 0.5 and obvious_hits:
        for ln in obvious_hits[:20]:  # 限制输出数量
            add(report, "DEAD-004", "Warning", ln,
                "过度注释: 注释只是复述显而易见的代码行为",
                "删除无信息量注释，只保留解释'为什么'的注释")


def detect_dead005_naming(report: FileReport, lines: List[str]) -> None:
    """DEAD-005 无意义命名：data1/temp/foo/bar/stuff/thing 等。"""
    seen: Set[str] = set()
    for i, line in enumerate(lines, 1):
        for m in MEANINGLESS_NAMES.finditer(line):
            name = m.group(1)
            key = f"{name}@{i}"
            if key in seen:
                continue
            seen.add(key)
            add(report, "DEAD-005", "Warning", i,
                f"无意义命名: 标识符 '{name}' 不传达任何业务含义",
                "用描述业务对象的名称替换（如 user_records 代替 data1）")


def detect_dead006_over_engineering(report: FileReport, lines: List[str],
                                    tree: Optional[ast.AST]) -> None:
    """DEAD-006 过度工程化：类只有静态方法/不必要工厂。"""
    lang = report.language
    if lang == "python" and tree is not None:
        class V(ast.NodeVisitor):
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                if py_class_only_static_methods(node):
                    add(report, "DEAD-006", "Warning", node.lineno,
                        f"过度工程化: 类 {node.name} 全是静态方法，"
                        "本质是命名空间而非对象，可用模块级函数替代",
                        "改为模块级函数，或若确为工具类则保留并说明")
                self.generic_visit(node)
        V().visit(tree)
    # 工厂模式只产一种产品（启发式）
    full = "\n".join(lines)
    factory_matches = re.findall(r"def\s+(create|make|build)\w*\s*\(", full)
    if len(factory_matches) >= 3:
        # 进一步看是否只 new 一种类型
        types = set(re.findall(r"return\s+(\w+)\(", full))
        if len(types) <= 1 and types:
            add(report, "DEAD-006", "Warning", 1,
                "过度工程化: 多个工厂函数但只生产一种产品类型",
                "删除多余工厂层，直接构造即可（YAGNI）")


def detect_dead007_repetitive(report: FileReport, lines: List[str],
                               tree: Optional[ast.AST]) -> None:
    """DEAD-007 重复模式：连续 3+ 相似 try-catch / if-else。"""
    lang = report.language
    if lang == "python" and tree is not None:
        for lineno, desc in py_find_repetitive_blocks(tree):
            add(report, "DEAD-007", "Warning", lineno, desc,
                "提取公共逻辑为辅助函数，用数据驱动消除重复块")
        return
    # 通用：连续 3+ 行以 try: / catch / if (... == 开头
    seq = 0
    start = 0
    prev_kind = ""
    for i, line in enumerate(lines, 1):
        s = line.strip()
        kind = ""
        if lang in ("c", "cpp", "rust", "go", "typescript", "javascript"):
            if s.startswith("try") or s.startswith("catch"):
                kind = "try"
            elif s.startswith("if") and "==" in s:
                kind = "if-eq"
        if kind and kind == prev_kind:
            seq += 1
            if seq == 1:
                start = i - 1
        else:
            if seq >= 3:
                add(report, "DEAD-007", "Warning", start,
                    f"连续 {seq} 个相似的 {prev_kind} 块，疑似重复模式",
                    "提取公共逻辑为辅助函数，用数据驱动消除重复块")
            seq = 1 if kind else 0
            start = i if kind else 0
            prev_kind = kind
    if seq >= 3:
        add(report, "DEAD-007", "Warning", start,
            f"连续 {seq} 个相似的 {prev_kind} 块，疑似重复模式",
            "提取公共逻辑为辅助函数，用数据驱动消除重复块")


def detect_dead008_fake_error(report: FileReport, lines: List[str],
                               tree: Optional[ast.AST]) -> None:
    """DEAD-008 虚假错误处理：空 except/pass / catch 只打印。"""
    lang = report.language
    if lang == "python" and tree is not None:
        for lineno, desc in py_find_trivial_excepts(tree):
            add(report, "DEAD-008", "Critical", lineno, desc,
                "要么真正处理异常，要么向上传播（raise），不要吞掉异常")
        return
    # 通用语言：空 catch 块 / catch 只 print
    for i, line in enumerate(lines, 1):
        s = line.strip()
        # catch (...) {}  /  } catch (e) {}
        if re.search(r"catch\s*\([^)]*\)\s*\{\s*\}", s):
            add(report, "DEAD-008", "Critical", i,
                "空 catch 块，异常被静默吞掉",
                "要么处理异常，要么 rethrow，不要空 catch")
        # catch 块下一行只有 print/console.log
        if re.match(r"^\s*(console\.log|print|fmt\.Println|println)\s*\(", s) \
                and i > 1 and "catch" in lines[i - 2]:
            add(report, "DEAD-008", "Critical", i,
                "catch 块只打印日志，未真正处理异常",
                "要么处理异常，要么向上抛出，不要只打印")


def detect_dead009_hallucinated_api(report: FileReport, lines: List[str]) -> None:
    """DEAD-009 幻觉API：调用不存在的标准库方法。"""
    lang = report.language
    for i, line in enumerate(lines, 1):
        for api_lang, pattern, note in HALLUCINATED_APIS:
            if api_lang != lang:
                continue
            if re.search(pattern, line):
                add(report, "DEAD-009", "Blocker", i,
                    f"疑似幻觉API: {note} (匹配行: {line.strip()[:80]})",
                    "查阅官方文档验证该 API 真实存在，修正方法名与签名")
                break


def detect_dead010_patchwork(report: FileReport, lines: List[str]) -> None:
    """DEAD-010 拼凑感：文件内 camelCase 与 snake_case 命名混用。"""
    camel_re = re.compile(r"\b[a-z][a-z0-9]*[A-Z]\w*\b")
    snake_re = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b")
    camel_count = 0
    snake_count = 0
    camel_examples: List[str] = []
    snake_examples: List[str] = []
    for line in lines:
        # 跳过字符串和注释粗略处理
        code = re.sub(r"(#|//).*$", "", line)
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'[^']*'", "''", code)
        for m in camel_re.findall(code):
            camel_count += 1
            if len(camel_examples) < 3:
                camel_examples.append(m)
        for m in snake_re.findall(code):
            snake_count += 1
            if len(snake_examples) < 3:
                snake_examples.append(m)
    # 阈值：两种命名各 >= 5 次，说明混用明显
    if camel_count >= 5 and snake_count >= 5:
        add(report, "DEAD-010", "Warning", 1,
            f"命名风格混用: camelCase({camel_count}次, 如 {camel_examples}) "
            f"与 snake_case({snake_count}次, 如 {snake_examples}) 共存，"
            "像拼接的代码",
            "统一为该语言的主流命名约定（Python/Rust 用 snake_case，"
            "JS/TS/Go/Java 用 camelCase）")


# --------------------------------------------------------------------------- #
# 主检测流程
# --------------------------------------------------------------------------- #

def analyze_file(path: str) -> FileReport:
    lang = detect_language(path) or "unknown"
    report = FileReport(path=path, language=lang)
    lines = read_lines(path)
    report.line_count = len(lines)
    if not lines:
        return report

    tree: Optional[ast.AST] = None
    if lang == "python":
        try:
            tree = ast.parse("\n".join(lines), filename=path)
        except SyntaxError:
            tree = None

    # 按模式逐个检测
    detect_dead001_dead_code(report, lines, tree)
    detect_dead002_placeholders(report, lines)
    detect_dead003_fake_impl(report, lines, tree)
    detect_dead004_over_comment(report, lines)
    detect_dead005_naming(report, lines)
    detect_dead006_over_engineering(report, lines, tree)
    detect_dead007_repetitive(report, lines, tree)
    detect_dead008_fake_error(report, lines, tree)
    detect_dead009_hallucinated_api(report, lines)
    detect_dead010_patchwork(report, lines)

    return report


def compute_score(reports: List[FileReport]) -> int:
    total = 0
    for r in reports:
        for f in r.findings:
            total += SEVERITY_WEIGHT.get(f.severity, 0)
    return min(total, 100)


def filter_by_severity(reports: List[FileReport], minimum: str) -> List[FileReport]:
    order = {"Warning": 0, "Critical": 1, "Blocker": 2}
    min_idx = order.get(minimum, 0)
    out: List[FileReport] = []
    for r in reports:
        kept = [f for f in r.findings if order.get(f.severity, 0) >= min_idx]
        if kept:
            nr = FileReport(path=r.path, language=r.language,
                            line_count=r.line_count, findings=kept)
            out.append(nr)
    return out


def build_json_report(reports: List[FileReport], score: int) -> Dict[str, Any]:
    severity_count = {"Blocker": 0, "Critical": 0, "Warning": 0}
    pattern_count: Dict[str, int] = {}
    for r in reports:
        for f in r.findings:
            severity_count[f.severity] = severity_count.get(f.severity, 0) + 1
            pattern_count[f.pattern_id] = pattern_count.get(f.pattern_id, 0) + 1
    return {
        "ai_flavor_score": score,
        "summary": {
            "files_scanned": len(reports),
            "total_findings": sum(len(r.findings) for r in reports),
            "by_severity": severity_count,
            "by_pattern": dict(sorted(pattern_count.items())),
        },
        "gate_passed": severity_count["Blocker"] == 0 and severity_count["Critical"] == 0,
        "files": [
            {
                "path": r.path,
                "language": r.language,
                "line_count": r.line_count,
                "findings": [asdict(f) for f in r.findings],
            }
            for r in reports if r.findings
        ],
    }


def print_human_report(reports: List[FileReport], score: int) -> None:
    print("=" * 72)
    print("反AI味检测报告 (Code Anti-AI-Flavor)")
    print("=" * 72)
    print(f"扫描文件数: {len(reports)}")
    total = sum(len(r.findings) for r in reports)
    print(f"发现总数: {total}")
    print(f"AI味评分: {score}/100 (越低越好，0=无AI味)")
    severity_count = {"Blocker": 0, "Critical": 0, "Warning": 0}
    for r in reports:
        for f in r.findings:
            severity_count[f.severity] += 1
    print(f"  Blocker: {severity_count['Blocker']}  "
          f"Critical: {severity_count['Critical']}  "
          f"Warning: {severity_count['Warning']}")
    gate = severity_count["Blocker"] == 0 and severity_count["Critical"] == 0
    print(f"质量门禁: {'PASS' if gate else 'FAIL (存在 Blocker/Critical，不可交付)'}")
    print("-" * 72)
    for r in reports:
        if not r.findings:
            continue
        print(f"\n[{r.language}] {r.path}  ({r.line_count} 行)")
        for f in r.findings:
            print(f"  [{f.severity}] {f.pattern_id} {f.location}")
            print(f"    症状: {f.symptom}")
            print(f"    修复: {f.remedy}")
    print("\n" + "=" * 72)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="detect_code_ai.py",
        description="检测代码中的 AI 味模式 (DEAD-001 ~ DEAD-010)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--target", help="要扫描的项目目录")
    group.add_argument("--file", help="要检测的单个文件")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--output", help="将报告写入指定文件（默认输出到 stdout）")
    parser.add_argument("--min-severity",
                        choices=["Warning", "Critical", "Blocker"],
                        default="Warning",
                        help="只显示该级别及以上的发现")
    parser.add_argument("--exclude", nargs="*",
                        default=["node_modules", ".git", "vendor",
                                 "__pycache__", "dist", "build", "target"],
                        help="要排除的目录名")
    args = parser.parse_args(argv)

    # 校验输入路径
    if args.target and not os.path.isdir(args.target):
        print(f"错误: 目标目录不存在: {args.target}", file=sys.stderr)
        return 2
    if args.file and not os.path.isfile(args.file):
        print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
        return 2

    files = collect_files(args.target, args.file, set(args.exclude))
    if not files:
        msg = "未找到任何支持的代码文件。"
        if args.json:
            payload = build_json_report([], 0)
            payload["summary"]["files_scanned"] = 0
            payload["note"] = msg
            _emit(payload, args)
        else:
            print(msg)
        return 0

    reports = [analyze_file(p) for p in files]
    reports = filter_by_severity(reports, args.min_severity)
    score = compute_score(reports)

    if args.json:
        payload = build_json_report(reports, score)
        _emit(payload, args)
    else:
        print_human_report(reports, score)
    return 0


def _emit(payload: Dict[str, Any], args: argparse.Namespace) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"报告已写入: {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    sys.exit(main())
