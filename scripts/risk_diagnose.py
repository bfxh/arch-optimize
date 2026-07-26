#!/usr/bin/env python3
"""arch-optimize: Risk Diagnosis (R1-R6)

Scans six architectural decay risks and emits structured findings using
the four-part Symptom -> Source -> Consequence -> Remedy format.

Risks:
  R1 认知过载 (Cognitive Overload)
  R2 变更传播 (Change Propagation)
  R3 知识重复 (Knowledge Duplication)
  R4 偶发复杂性 (Accidental Complexity)
  R5 依赖失序 (Dependency Disorder)
  R6 领域模型扭曲 (Domain Model Distortion)

Each finding is a dict with keys:
  risk, severity, location, symptom, source, consequence, remedy

Supports: Python, Go, C/C++, Rust, TypeScript/JavaScript
Dependencies: Python 3.8+ stdlib only

Usage:
    python3 risk_diagnose.py --target src/ --json
    python3 risk_diagnose.py --target . --risk R1 --risk R5
    python3 risk_diagnose.py --target . --min-severity Critical
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# ── Language detection ──────────────────────────────────────────────

LANG_EXTENSIONS = {
    ".py": "python",
    ".go": "go",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rs": "rust",
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
}

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__", ".cache",
    "dist", "build", "target", ".venv", "venv", ".idea", ".vscode", "testdata",
}

RISK_NAMES = {
    "R1": "认知过载 (Cognitive Overload)",
    "R2": "变更传播 (Change Propagation)",
    "R3": "知识重复 (Knowledge Duplication)",
    "R4": "偶发复杂性 (Accidental Complexity)",
    "R5": "依赖失序 (Dependency Disorder)",
    "R6": "领域模型扭曲 (Domain Model Distortion)",
}

SEVERITY_RANK = {"Critical": 3, "Warning": 2, "Suggestion": 1}

# Generic module names that do not match business vocabulary (R6)
GENERIC_NAMES = {
    "util", "utils", "helper", "helpers", "common", "misc", "manager",
    "managers", "service", "services", "handler", "handlers", "stuff",
    "tools", "toolkit", "core", "miscellaneous", "general",
}

# Infrastructure markers (R5): domain layer must not import these
INFRA_MARKERS = (
    "db", "database", "sql", "redis", "mongo", "kafka", "rabbitmq",
    "grpc", "protobuf", "proto", "net/http", "http", "infra", "infrastructure",
    "persistence", "repository", "filesystem", "os", "net", "cloud", "aws",
    "gcp", "azure", "s3", "elastic", "graphql",
)

# Composition roots are exempt from R5 layer-violation checks (false-positive guard)
COMPOSITION_ROOT_NAMES = {
    "main", "app", "index", "bootstrap", "wire", "server", "cmd", "container",
    "composition_root", "di", "injector", "startup", "run",
}

# DTO/persistence/payload markers exempt from R6 anemic-model detection
DTO_MARKERS = ("dto", "request", "response", "record", "schema", "payload",
               "vo", "bo", "entity", "model", "event", "message", "view")

# Algorithmic path markers exempt from R4 CC>20 Critical (still flagged Warning)
ALGO_MARKERS = ("algo", "algorithm", "sort", "search", "parse", "crypto",
                "math", "codec", "compress", "graph", "astar", "dfa", "nfa")

# ── File discovery & source reading ─────────────────────────────────

def discover_files(target):
    """Yield (filepath, lang) for every supported source file under target."""
    if os.path.isfile(target):
        ext = Path(target).suffix.lower()
        lang = LANG_EXTENSIONS.get(ext)
        if lang:
            yield target, lang
        return
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            lang = LANG_EXTENSIONS.get(ext)
            if lang:
                yield os.path.join(root, fname), lang


def read_source(filepath):
    """Read file contents as text, never raising."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def relpath(target, filepath):
    """Path relative to target (falls back to basename)."""
    try:
        rel = os.path.relpath(filepath, target).replace(os.sep, "/")
        # Single-file mode: relpath of a file against itself yields "."
        return rel if rel not in (".", "") else os.path.basename(filepath)
    except ValueError:
        return os.path.basename(filepath)


# ── Function extraction (R1/R3/R4 input) ────────────────────────────

FUNC_RE = {
    "go": re.compile(r"^func\s+(\w+)", re.MULTILINE),
    "c": re.compile(r"^\w[\w\s\*]*\s+(\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
    "cpp": re.compile(r"^\w[\w\s\*<>:,]*\s+(\w+)\s*\([^;]*\)\s*\{", re.MULTILINE),
    "rust": re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+(\w+)", re.MULTILINE),
    "typescript": re.compile(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", re.MULTILINE),
    "javascript": re.compile(r"^\s*(export\s+)?(async\s+)?function\s+(\w+)", re.MULTILINE),
}

DECISION_RE = {
    "go": re.compile(r"\b(if|else\s+if|for|switch|case|select|&&|\|\|)\b"),
    "c": re.compile(r"\b(if|else\s+if|for|while|case|catch|\?\s|&&|\|\||switch)\b"),
    "cpp": re.compile(r"\b(if|else\s+if|for|while|case|catch|\?\s|&&|\|\||switch)\b"),
    "rust": re.compile(r"\b(if|else\s+if|for|while|loop|match|=>|&&|\|\|)\b"),
    "typescript": re.compile(r"\b(if|else\s+if|for|while|case|catch|\?\s|&&|\|\||switch)\b"),
    "javascript": re.compile(r"\b(if|else\s+if|for|while|case|catch|\?\s|&&|\|\||switch)\b"),
}


def _python_nesting_depth(node):
    """Max depth of nested control-flow blocks within a function AST node."""
    control = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
               ast.Try, ast.ExceptHandler)

    def walk(n, current):
        best = current
        for child in ast.iter_child_nodes(n):
            if isinstance(child, control):
                best = max(best, walk(child, current + 1))
            else:
                best = max(best, walk(child, current))
        return best

    return walk(node, 0)


def _python_cc(node):
    """Cyclomatic complexity for a Python function AST node."""
    cc = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            cc += 1
        elif isinstance(child, ast.ExceptHandler):
            cc += 1
        elif isinstance(child, ast.BoolOp):
            cc += len(child.values) - 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp,
                                ast.GeneratorExp)):
            cc += 1
        elif isinstance(child, ast.Assert):
            cc += 1
    return cc


def _python_func_params(args):
    """Count positional/kw/vararg parameters on a Python function."""
    return (len(args.args) + len(args.kwonlyargs) + len(getattr(args, "posonlyargs", []))
            + (1 if args.vararg else 0) + (1 if args.kwarg else 0))


def _python_guard_clauses(node):
    """Heuristic count of early-return guard clauses at the top of a function."""
    guards = 0
    for child in node.body:
        if isinstance(child, ast.Return):
            guards += 1
        elif isinstance(child, ast.If) and any(isinstance(s, ast.Return) for s in child.body):
            guards += 1
        else:
            break  # only leading guards count
    return guards


def extract_functions_python(source):
    """Return list of function metadata dicts for a Python source string."""
    funcs = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return funcs
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append({
                "name": node.name,
                "line": node.lineno,
                "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                "params": _python_func_params(node.args),
                "nesting": _python_nesting_depth(node),
                "cc": _python_cc(node),
                "guards": _python_guard_clauses(node),
            })
    return funcs


def _brace_body_extent(lines, start_idx):
    """Return the inclusive end index of a brace-delimited body."""
    brace = 0
    started = False
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                brace += 1
                started = True
            elif ch == "}":
                brace -= 1
                if started and brace == 0:
                    return i
    return len(lines) - 1


def _brace_nesting(body_lines):
    """Approximate max nesting depth from brace counting."""
    depth = max_depth = 0
    for line in body_lines:
        for ch in line:
            if ch == "{":
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == "}":
                depth -= 1
    return max_depth


def _sig_param_count(sig_text):
    """Rough parameter count from a C-family function signature."""
    start, end = sig_text.find("("), sig_text.rfind(")")
    if start == -1 or end == -1 or end < start:
        return 0
    params = sig_text[start + 1:end].strip()
    if not params or params == "void":
        return 0
    count, angle = 0, 0
    for ch in params:
        if ch == "<":
            angle += 1
        elif ch == ">":
            angle -= 1
        elif ch == "," and angle == 0:
            count += 1
    return count + 1


def extract_functions_c_family(source, lang):
    """Return list of function metadata dicts for C-family source."""
    funcs = []
    func_re = FUNC_RE.get(lang)
    decision_re = DECISION_RE.get(lang)
    if not func_re or not decision_re:
        return funcs
    lines = source.split("\n")
    for match in func_re.finditer(source):
        name = next((g for g in match.groups() if g), None)
        if not name:
            continue
        start_idx = source[:match.start()].count("\n")
        end_idx = _brace_body_extent(lines, start_idx)
        body = "\n".join(lines[start_idx:end_idx + 1])
        funcs.append({
            "name": name,
            "line": start_idx + 1,
            "lines": end_idx - start_idx + 1,
            "params": _sig_param_count(match.group(0)),
            "nesting": max(0, _brace_nesting(lines[start_idx:end_idx + 1]) - 1),
            "cc": 1 + len(decision_re.findall(body)),
            "guards": body.count("return") + body.count("throw"),
        })
    return funcs


def extract_functions(source, lang):
    """Dispatch function extraction by language."""
    if lang == "python":
        return extract_functions_python(source)
    return extract_functions_c_family(source, lang)


# ── Import extraction (R2/R5 input) ─────────────────────────────────

PY_STDLIB_TOP = {
    "os", "sys", "re", "json", "math", "pathlib", "collections", "itertools",
    "functools", "typing", "argparse", "ast", "io", "time", "datetime",
    "logging", "unittest", "asyncio", "threading", "multiprocessing",
    "subprocess", "shutil", "glob", "hashlib", "base64", "random", "decimal",
    "dataclasses", "enum", "abc", "copy", "csv", "sqlite3", "socket",
    "urllib", "http", "xml", "html", "email", "contextlib", "inspect",
}


def _normalize_module(name):
    """Reduce a dotted module path to its top-level package name."""
    if not name:
        return ""
    return name.split(".")[0].lstrip(".")


def imports_python(source):
    """Return full dotted module paths (e.g. 'domain.order', 'os.path').

    Full paths are kept so R5 can resolve them to files for cycle detection;
    R2 normalizes to top-level packages itself when counting fan-out.
    """
    mods = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return mods
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Relative imports: prepend a marker so R5 can still try basename
            # resolution; absolute imports keep their full dotted path.
            if node.level and node.level > 0:
                mods.append(node.module or "")
            elif node.module:
                mods.append(node.module)
    return mods


def _regex_imports(source, pattern, group=1):
    """Helper: return all non-empty matches of a capture group."""
    return [m for m in pattern.findall(source) if m]


GO_IMPORT_RE = re.compile(r"import\s*(?:\(([^)]*)\)|"  # block form
                          r'"([^"]+)")', re.MULTILINE)
GO_QUOTED_RE = re.compile(r'"([^"]+)"')
C_INCLUDE_RE = re.compile(r'#\s*include\s*[<"]([^>"]+)[>"]')
RUST_USE_RE = re.compile(r'^\s*use\s+([\w:]+)', re.MULTILINE)
TS_IMPORT_RE = re.compile(r"""import\s+[^;]*?from\s+['"]([^'"]+)['"]""")
TS_REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")


def imports_go(source):
    """Return imported Go package paths."""
    mods = []
    for block, single in GO_IMPORT_RE.findall(source):
        if single:
            mods.append(single)
        else:
            mods.extend(GO_QUOTED_RE.findall(block))
    return mods


def imports_c_family(source):
    """Return included headers."""
    return _regex_imports(source, C_INCLUDE_RE)


def imports_rust(source):
    """Return Rust use paths reduced to the first two segments."""
    mods = []
    for raw in RUST_USE_RE.findall(source):
        segs = raw.split("::")
        mods.append("::".join(segs[:2]))
    return mods


def imports_ts_js(source):
    """Return TS/JS imported module specifiers."""
    return _regex_imports(source, TS_IMPORT_RE) + _regex_imports(source, TS_REQUIRE_RE)


def extract_imports(source, lang):
    """Return list of imported module strings for a file."""
    if lang == "python":
        return imports_python(source)
    if lang == "go":
        return imports_go(source)
    if lang in ("c", "cpp"):
        return imports_c_family(source)
    if lang == "rust":
        return imports_rust(source)
    return imports_ts_js(source)


# ── Layer classification (R5) ───────────────────────────────────────

LAYER_PATTERNS = [
    (re.compile(r"(^|/)(domain|entities|entity|model|aggregate)(/|$)"), 3),  # innermost
    (re.compile(r"(^|/)(usecase|use_case|application|app/service|services|command)(/|$)"), 2),
    (re.compile(r"(^|/)(api|controller|controllers|handler|handlers|presentation|ui|web|router)(/|$)"), 1),
    (re.compile(r"(^|/)(infra|infrastructure|persistence|repository|repositories|db|database|adapter|adapters|external|client)(/|$)"), 0),
]


def layer_rank(rel_path):
    """Return architectural layer rank (higher = more inner/protected)."""
    for pat, rank in LAYER_PATTERNS:
        if pat.search(rel_path):
            return rank
    return None


def is_composition_root(rel_path):
    """True for files that legitimately wire concrete dependencies."""
    base = Path(rel_path).stem.lower()
    if base in COMPOSITION_ROOT_NAMES:
        return True
    parts = rel_path.lower().split("/")
    return any(p in COMPOSITION_ROOT_NAMES for p in parts) or "cmd" in parts


def is_domain_layer(rel_path):
    """True if the file lives in a domain/core layer."""
    return layer_rank(rel_path) == 3


def imports_infra(modules):
    """True if any imported module references infrastructure."""
    low = " ".join(modules).lower()
    return any(marker in low for marker in INFRA_MARKERS)


# ── R1 Cognitive Overload ───────────────────────────────────────────

def detect_r1(filepath, lang, source, rel):
    """R1 认知过载: function length, nesting, params, CC."""
    findings = []
    for fn in extract_functions(source, lang):
        sev, issue = None, None
        if fn["lines"] > 50:
            sev, issue = "Critical", f"函数 {fn['lines']} 行 (>50)"
        elif fn["lines"] > 20:
            sev, issue = "Warning", f"函数 {fn['lines']} 行 (20-50)"
        if fn["nesting"] > 5:
            sev, issue = "Critical", f"嵌套 {fn['nesting']} 层 (>5)"
        elif fn["nesting"] in (4, 5) and sev != "Critical":
            sev, issue = "Warning", f"嵌套 {fn['nesting']} 层 (4-5)"
        if fn["cc"] > 15:
            sev, issue = "Critical", f"圈复杂度 CC={fn['cc']} (>15)"
        if fn["params"] > 4 and sev in (None, "Suggestion"):
            sev = "Warning"
            issue = (issue + "; " if issue else "") + f"参数 {fn['params']} 个 (>4)"

        if not sev:
            continue

        # False positive guard: linear + guard clauses + clear naming
        if (fn["lines"] > 50 and fn["nesting"] <= 2 and fn["cc"] <= 10
                and fn["guards"] >= 2 and len(fn["name"]) >= 4):
            sev = "Suggestion"
            issue += " [疑似假阳性: 线性+卫语句]"

        findings.append(_finding(
            "R1", sev, f"{rel}:{fn['name']}:{fn['line']}",
            symptom=f"{issue}，理解成本高",
            source="缺少中间抽象，条件/分支逻辑内联于单一函数",
            consequence="新成员理解耗时长，修改易引入缺陷，测试覆盖困难",
            remedy="提取卫语句前置、按职责拆分子函数、用策略/多态消除分支",
        ))
    return findings


# ── R2 Change Propagation ───────────────────────────────────────────

def detect_r2(filepath, lang, source, rel):
    """R2 变更传播: module fan-out via import count."""
    findings = []
    mods = extract_imports(source, lang)
    # Distinct external modules. For Python, count distinct top-level packages
    # (so domain.order/domain.billing count as one "domain" dependency) and
    # exclude stdlib + the module's own top-level package.
    if lang == "python":
        distinct = {_normalize_module(m) for m in mods}
        distinct = {m for m in distinct if m and m not in PY_STDLIB_TOP
                    and m != _normalize_module(Path(rel).stem)}
    else:
        distinct = {m for m in set(mods) if m}
    fan_out = len(distinct)

    if fan_out > 7:
        sev = "Critical"
    elif fan_out >= 5:
        sev = "Warning"
    else:
        return findings

    findings.append(_finding(
        "R2", sev, f"{rel}:module:{1}",
        symptom=f"模块扇出 fan-out={fan_out} ({'Critical' if fan_out > 7 else 'Warning'})",
        source="模块承担过多职责，直接依赖大量外部模块",
        consequence="任一依赖变动均需触碰本模块，变更波及面广，回归风险高",
        remedy="按业务能力拆分模块，通过接口/事件解耦，收敛对外依赖面",
    ))
    return findings


# ── R3 Knowledge Duplication ────────────────────────────────────────

TOKEN_RE = re.compile(r"\w+|[^\s\w]")
MAGIC_NUM_RE = re.compile(r"\b(?<![\w.])(\d{2,})(?!\w)")


def _strip_strings_comments(source, lang):
    """Roughly strip string literals and comments to reduce false positives."""
    if lang == "python":
        source = re.sub(r'#.*', '', source)
        source = re.sub(r'"""[\s\S]*?"""', '', source)
        source = re.sub(r"'''[\s\S]*?'''", '', source)
        source = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', source)
        source = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", source)
    else:
        source = re.sub(r'//.*', '', source)
        source = re.compile(r'/\*[\s\S]*?\*/').sub('', source)
        source = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', source)
        source = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", source)
        source = re.sub(r'`[^`]*`', '``', source)
    return source


def _func_tokens(source, lang, fn):
    """Token slice for a function body (approximate, by line range)."""
    lines = source.split("\n")
    body = "\n".join(lines[fn["line"] - 1: fn["line"] - 1 + fn["lines"]])
    return TOKEN_RE.findall(_strip_strings_comments(body, lang))


def _top_context(rel):
    """Top-level directory used as a bounded-context proxy."""
    parts = rel.split("/")
    return parts[0] if len(parts) > 1 else ""


def detect_r3(files_data):
    """R3 知识重复: token-gram similarity across functions + magic numbers."""
    findings = []
    # --- duplicate code blocks via 8-gram Jaccard ---
    NGRAM = 8
    inverted = defaultdict(set)  # ngram_hash -> {fid}
    func_records = []  # (fid, rel, fn, token_count)
    fid = 0
    for (filepath, lang, source, rel), funcs in files_data:
        for fn in funcs:
            if fn["lines"] < 10:
                continue
            toks = _func_tokens(source, lang, fn)
            if len(toks) < NGRAM:
                continue
            grams = {hash(tuple(toks[i:i + NGRAM])) for i in range(len(toks) - NGRAM + 1)}
            for g in grams:
                inverted[g].add(fid)
            func_records.append((fid, rel, fn, grams))
            fid += 1

    seen_pairs = set()
    for fid_a, rel_a, fn_a, grams_a in func_records:
        candidates = defaultdict(int)
        for g in grams_a:
            for fid_b in inverted[g]:
                if fid_b <= fid_a:
                    continue
                candidates[fid_b] += 1
        for fid_b, inter in candidates.items():
            if (fid_a, fid_b) in seen_pairs:
                continue
            seen_pairs.add((fid_a, fid_b))
            rel_b, fn_b, grams_b = (func_records[fid_b][1],
                                    func_records[fid_b][2],
                                    func_records[fid_b][3])
            union = len(grams_a | grams_b) or 1
            jac = inter / union
            if jac >= 0.6:
                # False positive: different bounded contexts
                ctx_a, ctx_b = _top_context(rel_a), _top_context(rel_b)
                if ctx_a and ctx_b and ctx_a != ctx_b:
                    continue
                sev = "Critical" if jac >= 0.8 else "Warning"
                findings.append(_finding(
                    "R3", sev, f"{rel_a}:{fn_a['name']}:{fn_a['line']}",
                    symptom=f"与 {rel_b}:{fn_b['name']} 代码块高度相似 (Jaccard={jac:.2f})",
                    source="同一决策/算法在多处复制粘贴，未提取共享抽象",
                    consequence="修改业务规则需同步多处，易遗漏导致行为不一致",
                    remedy="提取公共函数/基类/策略对象，单一事实来源表达该决策",
                ))

    # --- magic numbers appearing 3+ times across files ---
    num_locations = defaultdict(list)  # value -> [(rel, line)]
    for (filepath, lang, source, rel), _funcs in files_data:
        clean = _strip_strings_comments(source, lang)
        for i, line in enumerate(clean.split("\n"), 1):
            for m in MAGIC_NUM_RE.findall(line):
                num_locations[m].append((rel, i))
    for value, locs in num_locations.items():
        files_hit = {rel for rel, _ in locs}
        if len(locs) >= 3 and len(files_hit) >= 2:
            sample = locs[0]
            findings.append(_finding(
                "R3", "Critical", f"{sample[0]}:magic:{value}:{sample[1]}",
                symptom=f"魔法数字 {value} 重复出现 {len(locs)} 次跨 {len(files_hit)} 文件",
                source="业务常量未命名并集中定义，散落字面量",
                consequence="阈值/配置调整需逐处搜索修改，易遗漏且语义不明",
                remedy="提取为命名常量/配置项，单一来源引用",
            ))
    return findings


# ── R4 Accidental Complexity ────────────────────────────────────────

def detect_r4(filepath, lang, source, rel):
    """R4 偶发复杂性: single-impl interfaces, high-CC non-algo code, 1-variant factories."""
    findings = []
    funcs = extract_functions(source, lang)
    is_algo = any(m in rel.lower() for m in ALGO_MARKERS)

    # CC > 20 in non-algorithmic code = Critical; algorithmic = Warning
    for fn in funcs:
        if fn["cc"] > 20:
            sev = "Warning" if is_algo else "Critical"
            findings.append(_finding(
                "R4", sev, f"{rel}:{fn['name']}:{fn['line']}",
                symptom=f"圈复杂度 CC={fn['cc']} (>20)，{'算法场景' if is_algo else '非算法场景'}",
                source="分支逻辑过度膨胀，可能引入了问题本身不需要的复杂度",
                consequence="维护成本畸高，测试路径组合爆炸，缺陷易潜伏",
                remedy="评估是否可用查表/多态/管道拆解，剥离偶发复杂性",
            ))

    # Single-implementation interfaces / 1-variant factories (Python + TS/JS)
    if lang == "python":
        findings.extend(_r4_python(source, rel))
    elif lang in ("typescript", "javascript"):
        findings.extend(_r4_ts_js(source, rel))
    return findings


def _r4_python(source, rel):
    findings = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return findings
    # Collect ABC/Protocol base classes and their subclasses
    bases_to_subs = defaultdict(list)
    abstract_bases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = _ast_name(base)
                if name and ("ABC" in name or "Protocol" in name
                             or name.startswith("Abstract")):
                    abstract_bases.add(node.name)
                if name:
                    bases_to_subs[name].append(node.name)
    for iface in abstract_bases:
        subs = [s for s in bases_to_subs.get(iface, []) if s != iface]
        if len(subs) == 1:
            findings.append(_finding(
                "R4", "Warning", f"{rel}:{iface}:0",
                symptom=f"抽象类/接口 {iface} 仅有 1 个实现 ({subs[0]})",
                source="为单一变体引入接口/抽象，过度设计",
                consequence="增加间接层而无扩展收益，阅读与跳转成本上升",
                remedy="移除接口直到第二变体出现(YAGNI)，或合并接口与实现",
            ))
    # Factory classes with single variant
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and "Factory" in node.name:
            methods = [m for m in node.body
                       if isinstance(m, ast.FunctionDef) and not m.name.startswith("_")]
            if len(methods) <= 1:
                findings.append(_finding(
                    "R4", "Warning", f"{rel}:{node.name}:{node.lineno}",
                    symptom=f"工厂类 {node.name} 仅产出单一变体",
                    source="引入工厂模式但当前仅有一种产品变体",
                    consequence="抽象与间接层无对应扩展价值",
                    remedy="直接构造对象，待多变体出现再引入工厂",
                ))
    return findings


def _r4_ts_js(source, rel):
    findings = []
    iface_re = re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)", re.MULTILINE)
    impl_re = re.compile(r"class\s+(\w+)\s+implements\s+([\w,\s]+)")
    interfaces = {m for m in iface_re.findall(source)}
    impl_map = defaultdict(list)
    for cls, ifaces in impl_re.findall(source):
        for i in [x.strip() for x in ifaces.split(",") if x.strip()]:
            impl_map[i].append(cls)
    for iface in interfaces:
        impls = impl_map.get(iface, [])
        if len(impls) == 1:
            findings.append(_finding(
                "R4", "Warning", f"{rel}:{iface}:0",
                symptom=f"接口 {iface} 仅有 1 个实现 ({impls[0]})",
                source="为单一变体引入接口，过度设计",
                consequence="增加间接层而无扩展收益",
                remedy="移除接口直到第二变体出现(YAGNI)",
            ))
    return findings


# ── R5 Dependency Disorder ──────────────────────────────────────────

def _ast_name(node):
    """Extract a dotted name from an AST base/attribute node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_ast_name(node.value)}.{node.attr}"
    return None


def _resolve_import_to_file(mod, rel_files):
    """Best-effort: resolve an imported module string to a known file path."""
    if not mod:
        return None
    norm = mod.replace(".", "/").replace("\\", "/")
    # exact relative path match (with any supported extension)
    for ext in LANG_EXTENSIONS:
        candidate = norm + ext
        if candidate in rel_files:
            return candidate
        # try last 1-2 segments as basename match
        tail = norm.split("/")[-1] + ext
        matches = [f for f in rel_files if f.endswith("/" + tail) or f == tail]
        if len(matches) == 1:
            return matches[0]
    return None


def detect_r5(import_edges, rel_files):
    """R5 依赖失序: cycles, domain->infra, layer-direction violations."""
    findings = []
    seen_cycles = set()

    # --- circular dependencies (file-level, DFS) ---
    graph = defaultdict(set)
    for src, dst in import_edges:
        if dst and dst != src:
            graph[src].add(dst)

    def dfs_cycles():
        cycles = []
        WHITE, GRAY, BLACK = 0, 1, 2
        color = defaultdict(int)

        def visit(node, stack):
            color[node] = GRAY
            stack.append(node)
            for nxt in graph.get(node, ()):
                if color.get(nxt, WHITE) == GRAY:
                    idx = stack.index(nxt)
                    cyc = tuple(sorted(stack[idx:]))
                    if cyc not in seen_cycles:
                        seen_cycles.add(cyc)
                        cycles.append(stack[idx:] + [nxt])
                elif color.get(nxt, WHITE) == WHITE:
                    visit(nxt, stack)
            stack.pop()
            color[node] = BLACK

        for n in list(graph.keys()):
            if color.get(n, WHITE) == WHITE:
                visit(n, [])
        return cycles

    for cyc in dfs_cycles():
        chain = " -> ".join(cyc)
        findings.append(_finding(
            "R5", "Critical", f"{cyc[0]}:cycle:{cyc[1] if len(cyc) > 1 else '?'}:0",
            symptom=f"循环依赖: {chain}",
            source="模块间双向耦合，未通过接口反转或共享下沉解耦",
            consequence="无法独立编译/测试/复用任一节点，变更沿环传播",
            remedy="提取共享模块到下层，或通过接口/事件反转其中一条边",
        ))

    # --- domain -> infrastructure & layer-direction violations ---
    for src, dst in import_edges:
        if not dst or dst == src:
            continue
        src_root = is_composition_root(src)
        if src_root:
            continue  # composition root is exempt (false-positive guard)
        src_rank = layer_rank(src)
        dst_rank = layer_rank(dst)
        # domain layer importing infrastructure
        if is_domain_layer(src) and imports_infra([dst]):
            findings.append(_finding(
                "R5", "Critical", f"{src}:import:{dst}:0",
                symptom=f"领域层 {src} 直接依赖基础设施 {dst}",
                source="领域层导入数据库/HTTP/文件系统等具体实现，违反依赖倒置",
                consequence="领域逻辑与基础设施耦合，无法脱离框架测试，迁移代价高",
                remedy="在领域层定义端口接口，基础设施实现接口并在组合根注入",
            ))
            continue
        # layer direction violation (inner depending on outer)
        if src_rank is not None and dst_rank is not None and dst_rank < src_rank and src_rank >= 2:
            findings.append(_finding(
                "R5", "Critical", f"{src}:import:{dst}:0",
                symptom=f"层间反向依赖: {src}(rank={src_rank}) -> {dst}(rank={dst_rank})",
                source="内层依赖了更外层模块，依赖方向未朝领域中心收敛",
                consequence="内层被外层变化绑架，分层失效，回归面扩大",
                remedy="反转依赖：外层依赖内层接口，或通过事件/端口解耦",
            ))
    return findings


# ── R6 Domain Model Distortion ──────────────────────────────────────

def detect_r6(filepath, lang, source, rel):
    """R6 领域模型扭曲: anemic models, naming mismatch, cross-context leakage."""
    findings = []
    parts = rel.lower().split("/")
    # module name not matching business vocabulary
    for part in parts[:-1]:
        if part in GENERIC_NAMES:
            findings.append(_finding(
                "R6", "Warning", f"{rel}:module:{part}:0",
                symptom=f"模块名 '{part}' 属通用技术词汇，非业务概念",
                source="未采用统一语言(Ubiquitous Language)命名模块",
                consequence="业务语义被技术术语掩盖，沟通与代码映射困难",
                remedy="按业务领域命名模块(如 order/billing/shipment)",
            ))
            break

    # cross-context logic leakage (heuristic keyword scan)
    context_keywords = {
        "billing": ["invoice", "payment", "charge", "refund", "price", "tax"],
        "shipping": ["delivery", "carrier", "tracking", "shipment"],
        "inventory": ["stock", "warehouse", "sku"],
        "auth": ["login", "token", "password", "session"],
    }
    current_ctx = next((c for c in context_keywords if c in parts), None)
    if current_ctx:
        leaked = []
        for ctx, kws in context_keywords.items():
            if ctx == current_ctx:
                continue
            for kw in kws:
                if re.search(rf"\b{kw}\w*\b", source, re.IGNORECASE):
                    leaked.append((ctx, kw))
                    break
        for ctx, kw in leaked[:3]:
            findings.append(_finding(
                "R6", "Warning", f"{rel}:leak:{kw}:0",
                symptom=f"{current_ctx} 模块内出现 {ctx} 上下文概念 ({kw})",
                source="限界上下文边界泄漏，跨域逻辑未通过翻译/防腐层",
                consequence="上下文耦合，职责模糊，模型表达失真",
                remedy="通过防腐层/领域事件解耦，将逻辑归还对应上下文",
            ))

    # anemic domain models (Python only — needs AST)
    if lang == "python":
        findings.extend(_r6_python_anemic(source, rel))
    return findings


def _r6_python_anemic(source, rel):
    findings = []
    try:
        tree = ast.parse(source)
    except (SyntaxError, Exception):
        return findings
    in_dto_dir = any(m in rel.lower() for m in ("/dto", "/model", "/api", "/proto",
                                                 "/schema", "/request", "/response"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        name = node.name
        # false positive: DTO/persistence/API payloads
        if name.endswith(("DTO", "Dto", "Request", "Response", "Record", "Schema",
                          "Payload", "Event", "Message")) or in_dto_dir:
            continue
        # only inspect classes that look like domain objects (CapWords, not *Service/*Controller)
        if name.endswith(("Service", "Controller", "Handler", "Manager", "Factory",
                          "Repository", "Provider", "Builder", "Validator")):
            continue
        methods = [m for m in node.body if isinstance(m, ast.FunctionDef)]
        behavioral = [m for m in methods
                      if not m.name.startswith("_")
                      and not isinstance(next(iter(m.decorator_list), None), property)
                      and m.name not in ("get", "set", "is", "has")]
        # property getters/setters only
        prop_methods = [m for m in methods
                        if any(isinstance(d, property) or _ast_name(d) == "property"
                               for d in m.decorator_list)]
        if methods and not behavioral and len(prop_methods) >= 1:
            findings.append(_finding(
                "R6", "Critical", f"{rel}:{name}:{node.lineno}",
                symptom=f"领域对象 {name} 仅含 getter/setter，无行为方法",
                source="业务逻辑外溢到 Service 层，领域对象退化为数据袋",
                consequence="领域规则分散且不可复用，不变量无法被对象自身保护",
                remedy="将相关业务行为迁回领域对象，让对象封装自身不变量",
            ))
    return findings


# ── Finding assembly & aggregation ──────────────────────────────────

def _finding(risk, severity, location, symptom, source, consequence, remedy):
    """Build a four-part finding dict."""
    return {
        "risk": risk,
        "risk_name": RISK_NAMES[risk],
        "severity": severity,
        "location": location,
        "symptom": symptom,
        "source": source,
        "consequence": consequence,
        "remedy": remedy,
    }


def compute_health_impact(findings):
    """Health score impact following the 100 - 15*C - 5*W - 1*S formula."""
    c = sum(1 for f in findings if f["severity"] == "Critical")
    w = sum(1 for f in findings if f["severity"] == "Warning")
    s = sum(1 for f in findings if f["severity"] == "Suggestion")
    score = max(0, 100 - 15 * c - 5 * w - 1 * s)
    if score >= 90:
        grade = "优秀"
    elif score >= 70:
        grade = "良好"
    elif score >= 50:
        grade = "需关注"
    else:
        grade = "危险"
    return {"score": score, "grade": grade, "critical": c, "warning": w, "suggestion": s}


def diagnose(target, risks, min_severity):
    """Run selected risk detectors across all files and return a full report."""
    files_data = []  # (filepath, lang, source, rel)
    import_edges = []  # (src_rel, imported_module_or_resolved)
    rel_files = set()

    for filepath, lang in discover_files(target):
        source = read_source(filepath)
        if not source:
            continue
        rel = relpath(target, filepath)
        files_data.append((filepath, lang, source, rel))
        rel_files.add(rel)

    # Pre-compute function lists per file (reused by R1/R3/R4)
    funcs_per_file = [(fd, extract_functions(fd[2], fd[1])) for fd in files_data]

    # Build import edges for R5 (resolve to in-repo files where possible)
    for filepath, lang, source, rel in files_data:
        mods = extract_imports(source, lang)
        for m in mods:
            resolved = _resolve_import_to_file(m, rel_files)
            import_edges.append((rel, resolved or m))

    all_findings = []
    if "R1" in risks:
        for (filepath, lang, source, rel), _ in funcs_per_file:
            all_findings.extend(detect_r1(filepath, lang, source, rel))
    if "R2" in risks:
        for filepath, lang, source, rel in files_data:
            all_findings.extend(detect_r2(filepath, lang, source, rel))
    if "R3" in risks:
        all_findings.extend(detect_r3(funcs_per_file))
    if "R4" in risks:
        for filepath, lang, source, rel in files_data:
            all_findings.extend(detect_r4(filepath, lang, source, rel))
    if "R5" in risks:
        all_findings.extend(detect_r5(import_edges, rel_files))
    if "R6" in risks:
        for filepath, lang, source, rel in files_data:
            all_findings.extend(detect_r6(filepath, lang, source, rel))

    # Apply severity filter
    min_rank = SEVERITY_RANK[min_severity]
    all_findings = [f for f in all_findings if SEVERITY_RANK[f["severity"]] >= min_rank]

    # Sort: by risk, then severity desc
    all_findings.sort(key=lambda f: (f["risk"], -SEVERITY_RANK[f["severity"]], f["location"]))

    health = compute_health_impact(all_findings)
    grouped = defaultdict(list)
    for f in all_findings:
        grouped[f["risk"]].append(f)

    return {
        "target": target,
        "files_analyzed": len(files_data),
        "risks_scanned": sorted(risks),
        "total_findings": len(all_findings),
        "health_score": health,
        "findings_by_risk": {r: grouped[r] for r in sorted(grouped)},
        "findings": all_findings,
    }


# ── Output formatting ───────────────────────────────────────────────

def _severity_marker(sev):
    return {"Critical": "[!]", "Warning": "[~]", "Suggestion": "[i]"}.get(sev, "[?]")


def render_human(report):
    """Render a human-readable report to stdout."""
    bar = "=" * 64
    dash = "-" * 64
    print(f"\n{bar}")
    print(f"  arch-optimize Risk Diagnosis Report (R1-R6)")
    print(f"{bar}")
    print(f"  Target:          {report['target']}")
    print(f"  Files analyzed:  {report['files_analyzed']}")
    print(f"  Risks scanned:   {', '.join(report['risks_scanned'])}")
    hs = report["health_score"]
    print(f"  Health Score:    {hs['score']}/100 ({hs['grade']})")
    print(f"  Critical:        {hs['critical']}")
    print(f"  Warning:         {hs['warning']}")
    print(f"  Suggestion:      {hs['suggestion']}")
    print(f"  Total findings:  {report['total_findings']}")

    if not report["findings"]:
        print(f"\n  No findings matching the filter. Architecture looks healthy.\n")
        print(f"{bar}\n")
        return

    for risk in sorted(report["findings_by_risk"]):
        items = report["findings_by_risk"][risk]
        print(f"\n  {dash}")
        print(f"  {risk} {RISK_NAMES[risk]}  ({len(items)} findings)")
        print(f"  {dash}")
        for f in items:
            print(f"\n  {_severity_marker(f['severity'])} [{f['severity']}] {f['location']}")
            print(f"      Symptom:     {f['symptom']}")
            print(f"      Source:      {f['source']}")
            print(f"      Consequence: {f['consequence']}")
            print(f"      Remedy:      {f['remedy']}")
    print(f"\n{bar}\n")


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="arch-optimize: Risk Diagnosis (R1-R6)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --target src/
  %(prog)s --target . --json
  %(prog)s --target . --risk R1 --risk R5
  %(prog)s --target . --min-severity Critical
        """,
    )
    parser.add_argument("--file", help="Analyze a single file")
    parser.add_argument("--target", help="Analyze a directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--risk", action="append",
                        choices=["R1", "R2", "R3", "R4", "R5", "R6"],
                        help="Scan only specific risk(s); repeatable")
    parser.add_argument("--min-severity", choices=["Critical", "Warning", "Suggestion"],
                        default="Suggestion", help="Minimum severity to report")
    args = parser.parse_args()

    if not args.file and not args.target:
        parser.print_help()
        sys.exit(1)

    target = args.file or args.target
    risks = args.risk if args.risk else ["R1", "R2", "R3", "R4", "R5", "R6"]
    report = diagnose(target, risks, args.min_severity)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        render_human(report)


if __name__ == "__main__":
    main()
