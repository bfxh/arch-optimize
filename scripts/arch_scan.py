#!/usr/bin/env python3
"""arch-optimize: Architecture Scanner (Stage 1 - Architecture Perception)

Scans a project directory and produces an architecture overview:
directory tree, entry points, tech stack, architecture docs, and a
module dependency summary (fan-in / fan-out).

Dependencies: Python 3.8+ stdlib only

Usage:
    python3 arch_scan.py --target .
    python3 arch_scan.py --target src/ --json
    python3 arch_scan.py --target . --depth 3
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__",
    ".cache", "dist", "build", "target", ".venv",
}

LANG_EXTENSIONS = {
    ".py": "Python",
    ".go": "Go",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".rs": "Rust",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".java": "Java", ".kt": "Kotlin",
}

# Files that mark a directory as a module boundary
MODULE_MARKERS = {
    "go.mod", "package.json", "Cargo.toml", "__init__.py",
    "CMakeLists.txt", "build.gradle", "pom.xml",
}

# Entry point file names
ENTRY_POINT_FILES = {
    "main.go", "main.py", "__main__.py", "app.py", "manage.py", "setup.py",
    "main.c", "main.cpp", "main.rs",
    "index.ts", "index.js", "app.ts", "server.ts", "main.ts",
}

# Entry point directories
ENTRY_POINT_DIRS = {"cmd", "src/bin", "bin"}

# Build system files in priority order
BUILD_FILES = [
    "go.mod", "package.json", "Cargo.toml", "CMakeLists.txt",
    "Makefile", "build.gradle", "pom.xml",
]

# Architecture documents to locate (priority order)
ARCH_DOCS = [
    "SPEC.md", "CLAUDE.md", "REASONIX.md", "ARCHITECTURE.md",
    "DESIGN.md", "CONTRIBUTING.md", "README.md",
]

# Framework keywords per config file: { config: { keyword: label } }
FRAMEWORK_PATTERNS = {
    "package.json": {
        "react": "React", "vue": "Vue", "next": "Next.js",
        "express": "Express", "nestjs": "NestJS", "@nestjs": "NestJS",
        "angular": "Angular", "svelte": "Svelte", "fastify": "Fastify",
        "nuxt": "Nuxt",
    },
    "go.mod": {
        "gin-gonic/gin": "Gin", "gorilla/mux": "Gorilla Mux",
        "labstack/echo": "Echo", "gofiber/fiber": "Fiber",
        "go-chi/chi": "Chi", "spf13/cobra": "Cobra", "gorm.io/gorm": "GORM",
    },
    "Cargo.toml": {
        "tokio": "Tokio", "serde": "Serde", "actix-web": "Actix Web",
        "rocket": "Rocket", "axum": "Axum", "warp": "Warp",
        "clap": "Clap", "reqwest": "Reqwest",
    },
}

PYTHON_FRAMEWORKS = {
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "torch": "PyTorch", "tensorflow": "TensorFlow",
    "scrapy": "Scrapy", "celery": "Celery",
}

# Test framework markers (file basename -> label)
TEST_FRAMEWORK_FILES = {
    "pytest.ini": "pytest",
    "jest.config.js": "Jest", "jest.config.ts": "Jest", "jest.config.json": "Jest",
    ".mocharc.yml": "Mocha", ".mocharc.js": "Mocha",
    "CTestTestfile.cmake": "CTest",
}

MAX_CHILDREN_PER_NODE = 100


# ── Directory scanning ─────────────────────────────────────────────

def _normalize(rel):
    """Normalize a relative path to forward slashes."""
    return rel.replace(os.sep, "/")


def collect_files(target, max_depth):
    """Collect (rel, full) for all files respecting ignore dirs and depth."""
    result = []
    target_abs = os.path.abspath(target)
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel_root = _normalize(os.path.relpath(root, target_abs))
        depth = 0 if rel_root == "." else rel_root.count("/") + 1
        if depth > max_depth:
            dirs[:] = []
            continue
        for fname in files:
            full = os.path.join(root, fname)
            rel = _normalize(os.path.relpath(full, target_abs))
            result.append((rel, full))
    return result


def scan_tree(target, max_depth):
    """Build a nested directory tree structure up to max_depth."""
    target_abs = os.path.abspath(target)
    root_name = os.path.basename(target_abs) or target
    return {
        "name": root_name,
        "type": "dir",
        "path": ".",
        "children": _scan_children(target_abs, target_abs, 1, max_depth),
    }


def _scan_children(abs_root, dir_path, depth, max_depth):
    children = []
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError:
        return children
    for entry in entries:
        if entry in IGNORE_DIRS:
            continue
        full = os.path.join(dir_path, entry)
        rel = _normalize(os.path.relpath(full, abs_root))
        if os.path.isdir(full):
            child = {"name": entry, "type": "dir", "path": rel}
            child["children"] = (_scan_children(abs_root, full, depth + 1, max_depth)
                                 if depth < max_depth else [])
            children.append(child)
        else:
            children.append({"name": entry, "type": "file", "path": rel})
        if len(children) >= MAX_CHILDREN_PER_NODE:
            children.append({"name": "... (truncated)", "type": "marker", "path": ""})
            break
    return children


def _count_dirs(node):
    """Count directory nodes in a tree."""
    count = 0
    if node.get("type") == "dir":
        count += 1
        for child in node.get("children", []):
            count += _count_dirs(child)
    return count


# ── Tech stack detection ───────────────────────────────────────────

def detect_languages(files):
    """Count files by language based on extension."""
    counts = {}
    total = 0
    for rel, _ in files:
        lang = LANG_EXTENSIONS.get(Path(rel).suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
            total += 1
    languages = []
    for name, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        pct = round(cnt / total * 100, 1) if total else 0.0
        languages.append({"name": name, "file_count": cnt, "percentage": pct})
    return languages


def detect_build_system(files):
    """Detect primary build system from config files (root first)."""
    root_names = {os.path.basename(rel) for rel, _ in files if "/" not in rel}
    any_names = {os.path.basename(rel) for rel, _ in files}
    for bf in BUILD_FILES:
        if bf in root_names:
            return bf
    for bf in BUILD_FILES:
        if bf in any_names:
            return bf
    return None


def detect_frameworks(files):
    """Detect frameworks from config files and dependency manifests."""
    found = []
    by_name = {}
    for rel, full in files:
        by_name.setdefault(os.path.basename(rel), full)
    # Node
    pkg = by_name.get("package.json")
    if pkg:
        try:
            with open(pkg, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            deps = {}
            deps.update(data.get("dependencies", {}) or {})
            deps.update(data.get("devDependencies", {}) or {})
            for key, label in FRAMEWORK_PATTERNS["package.json"].items():
                if any(key in dep for dep in deps):
                    found.append(label)
        except Exception:
            pass
    # Go
    gomod = by_name.get("go.mod")
    if gomod:
        try:
            content = open(gomod, encoding="utf-8", errors="replace").read()
            for key, label in FRAMEWORK_PATTERNS["go.mod"].items():
                if key in content:
                    found.append(label)
        except Exception:
            pass
    # Rust
    cargo = by_name.get("Cargo.toml")
    if cargo:
        try:
            content = open(cargo, encoding="utf-8", errors="replace").read()
            for key, label in FRAMEWORK_PATTERNS["Cargo.toml"].items():
                if key in content:
                    found.append(label)
        except Exception:
            pass
    # Python
    py_source = ""
    for pyf in ("requirements.txt", "setup.py"):
        if by_name.get(pyf):
            try:
                py_source += "\n" + open(by_name[pyf], encoding="utf-8",
                                         errors="replace").read().lower()
            except Exception:
                pass
    for key, label in PYTHON_FRAMEWORKS.items():
        if key in py_source:
            found.append(label)
    seen = set()
    return [fw for fw in found if not (fw in seen or seen.add(fw))]


def detect_test_frameworks(files):
    """Detect test frameworks from config files and test file patterns."""
    found = []
    name_set = {os.path.basename(rel) for rel, _ in files}
    for marker, label in TEST_FRAMEWORK_FILES.items():
        if marker in name_set:
            found.append(label)
    if any(os.path.basename(rel).endswith("_test.go") for rel, _ in files):
        found.append("go test")
    if any(os.path.basename(rel).endswith("_test.rs") for rel, _ in files):
        found.append("cargo test")
    if (any(os.path.basename(rel).startswith("test_") and rel.endswith(".py")
            for rel, _ in files) and "pytest" not in found):
        found.append("pytest/unittest")
    seen = set()
    return [t for t in found if not (t in seen or seen.add(t))]


# ── Entry point detection ──────────────────────────────────────────

def detect_entry_points(target, files):
    """Detect entry point files and directories."""
    entry_points = []
    for rel, _ in files:
        fname = os.path.basename(rel)
        if fname in ENTRY_POINT_FILES:
            lang = LANG_EXTENSIONS.get(Path(rel).suffix.lower(), "unknown")
            entry_points.append({"path": rel, "name": fname,
                                 "language": lang, "type": "file"})
    for epd in ENTRY_POINT_DIRS:
        if os.path.isdir(os.path.join(target, *epd.split("/"))):
            entry_points.append({"path": epd, "name": epd,
                                 "language": "unknown", "type": "directory"})
    return entry_points


# ── Architecture docs ──────────────────────────────────────────────

def locate_arch_docs(target, files):
    """Locate architecture documents and read first-line descriptions."""
    docs = []
    # Prefer root-level docs; fall back to nested occurrences
    by_name = {}
    for rel, full in files:
        bn = os.path.basename(rel)
        if bn in ARCH_DOCS:
            if bn not in by_name or "/" not in rel:
                by_name[bn] = (rel, full)
    for doc_name in ARCH_DOCS:
        if doc_name in by_name:
            rel, full = by_name[doc_name]
            desc = ""
            try:
                first = open(full, encoding="utf-8", errors="replace").readline().strip()
                desc = first.lstrip("#").strip()
            except Exception:
                pass
            docs.append({"name": doc_name, "path": rel, "description": desc})
    if os.path.isdir(os.path.join(target, "docs")):
        docs.append({"name": "docs/", "path": "docs",
                     "description": "documentation directory"})
    return docs


# ── Module detection & dependency analysis ─────────────────────────

def detect_modules(files, max_depth):
    """Detect module boundaries.

    A directory is a module if it directly contains a source file or a
    module marker (go.mod, package.json, Cargo.toml, __init__.py, ...).
    This yields package-level modules such as 'internal/agent'.
    """
    module_dirs = {}
    for rel, _ in files:
        bn = os.path.basename(rel)
        dir_rel = os.path.dirname(rel) or "."
        depth = 0 if dir_rel == "." else dir_rel.count("/") + 1
        if depth > max_depth:
            continue
        if bn in MODULE_MARKERS or Path(rel).suffix.lower() in LANG_EXTENSIONS:
            module_dirs.setdefault(dir_rel, set()).add(bn)
    return module_dirs


def extract_imports(filepath, lang):
    """Extract import paths from a source file."""
    try:
        source = open(filepath, encoding="utf-8", errors="replace").read()
    except Exception:
        return []
    imports = []
    if lang == "Go":
        for m in re.finditer(r'^import\s+"([^"]+)"', source, re.MULTILINE):
            imports.append(m.group(1))
        for block in re.finditer(r'^import\s*\(([^)]*)\)', source, re.MULTILINE | re.DOTALL):
            imports.extend(re.findall(r'"([^"]+)"', block.group(1)))
    elif lang == "Python":
        for m in re.finditer(r'^\s*from\s+([\w.]+)\s+import', source, re.MULTILINE):
            imports.append(m.group(1))
        for m in re.finditer(r'^\s*import\s+([\w.]+)', source, re.MULTILINE):
            imports.append(m.group(1))
    elif lang == "Rust":
        for m in re.finditer(r'\buse\s+([\w:]+)', source):
            imports.append(m.group(1).replace("::", "/"))
    elif lang in ("TypeScript", "JavaScript"):
        imports.extend(re.findall(r'from\s+["\']([^"\']+)["\']', source))
        imports.extend(re.findall(r'require\(\s*["\']([^"\']+)["\']\s*\)', source))
    elif lang in ("C", "C++"):
        imports.extend(re.findall(r'#include\s*"([^"]+)"', source))
    elif lang == "Java":
        imports.extend(re.findall(r'import\s+([\w.]+)\s*;', source))
    return imports


def _resolve_import_to_module(imp, source_module, modules):
    """Resolve an import string to a target module path (heuristic)."""
    norm = imp.replace("\\", "/").strip("./")
    norm_slash = "/" + norm + "/"
    # Path-based match for nested modules (bounded by separators)
    for m in modules:
        if m in (".", source_module) or "/" not in m:
            continue
        if ("/" + m + "/") in norm_slash:
            return m
    # Segment-based match for top-level modules
    segments = [s for s in re.split(r"[/.:]+", norm) if s]
    for m in modules:
        if m in (".", source_module) or "/" in m:
            continue
        if m and m in segments:
            return m
    return None


def analyze_modules(target, files, modules):
    """Analyze module dependencies: file counts, fan-in, fan-out."""
    target_abs = os.path.abspath(target)
    root_name = os.path.basename(target_abs) or "root"
    module_files = {m: [] for m in modules}

    # Assign each source file to its nearest enclosing module
    for rel, full in files:
        lang = LANG_EXTENSIONS.get(Path(rel).suffix.lower())
        if not lang:
            continue
        file_dir = os.path.dirname(rel) or "."
        assigned = None
        check_dir = file_dir
        while True:
            if check_dir in modules:
                assigned = check_dir
                break
            if "/" not in check_dir:
                if "." in modules:
                    assigned = "."
                break
            check_dir = "/".join(check_dir.split("/")[:-1]) or "."
        if assigned and assigned in module_files:
            module_files[assigned].append((rel, full, lang))

    module_info = {}
    for m in modules:
        mname = m if m != "." else root_name
        module_info[m] = {
            "name": mname, "path": m, "files": len(module_files[m]),
            "fan_out": 0, "fan_in": 0, "_out": set(), "_in": set(),
        }

    for m in modules:
        for rel, full, lang in module_files[m]:
            for imp in extract_imports(full, lang):
                tgt = _resolve_import_to_module(imp, m, modules)
                if tgt and tgt in module_info and tgt != m:
                    module_info[m]["_out"].add(tgt)
                    module_info[tgt]["_in"].add(m)

    result = []
    for m, info in module_info.items():
        info["fan_out"] = len(info.pop("_out"))
        info["fan_in"] = len(info.pop("_in"))
        result.append(info)
    result.sort(key=lambda x: (-x["files"], x["name"]))
    return result


# ── Main scan ──────────────────────────────────────────────────────

def scan_project(target, max_depth):
    """Run full architecture scan and return structured result."""
    target_abs = os.path.abspath(target)
    files = collect_files(target_abs, max_depth)
    modules_map = detect_modules(files, max_depth)
    module_list = analyze_modules(target_abs, files, modules_map)
    return {
        "target": target_abs,
        "scan_timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "directory_tree": scan_tree(target_abs, max_depth),
        "entry_points": detect_entry_points(target_abs, files),
        "tech_stack": {
            "languages": detect_languages(files),
            "build_system": detect_build_system(files),
            "frameworks": detect_frameworks(files),
            "test_frameworks": detect_test_frameworks(files),
        },
        "architecture_docs": locate_arch_docs(target_abs, files),
        "modules": [
            {"name": m["name"], "path": m["path"], "files": m["files"],
             "fan_in": m["fan_in"], "fan_out": m["fan_out"]}
            for m in module_list
        ],
        "summary": {
            "total_files": len(files),
            "total_dirs": _count_dirs(scan_tree(target_abs, max_depth)),
            "total_modules": len(modules_map),
        },
    }


# ── Human-readable output ──────────────────────────────────────────

def print_tree(node, prefix="", is_last=True, counter=None):
    """Print a filtered tree view (dirs + notable files)."""
    if counter is None:
        counter = [0]
    if counter[0] >= 60:
        if counter[0] == 60:
            print(f"{prefix}... (tree truncated)")
            counter[0] += 1
        return
    connector = "└── " if is_last else "├── "
    suffix = "/" if node.get("type") == "dir" else ""
    print(f"{prefix}{connector}{node['name']}{suffix}")
    counter[0] += 1
    if node.get("type") == "dir":
        children = node.get("children", [])
        notable_exts = {".py", ".go", ".rs", ".ts", ".js", ".cpp", ".c", ".java"}
        shown = []
        for c in children:
            if c.get("type") in ("dir", "marker"):
                shown.append(c)
            elif c.get("type") == "file":
                fn = c["name"]
                ext = Path(fn).suffix.lower()
                if (fn in ENTRY_POINT_FILES or fn in MODULE_MARKERS
                        or fn in BUILD_FILES or fn in ARCH_DOCS or ext in notable_exts):
                    shown.append(c)
        shown = shown[:30]
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(shown):
            print_tree(child, new_prefix, i == len(shown) - 1, counter)


def print_human_readable(result):
    """Print a human-readable architecture overview."""
    print(f"\n{'='*60}")
    print(f"  arch-optimize Architecture Scan (Stage 1: Perception)")
    print(f"{'='*60}")
    print(f"  Target:      {result['target']}")
    print(f"  Scanned:     {result['scan_timestamp']}")
    s = result["summary"]
    print(f"  Files:       {s['total_files']}")
    print(f"  Directories: {s['total_dirs']}")
    print(f"  Modules:     {s['total_modules']}")

    print(f"\n  {'─'*56}")
    print(f"  Directory Structure:")
    print(f"  {'─'*56}")
    print_tree(result["directory_tree"])

    ts = result["tech_stack"]
    print(f"\n  {'─'*56}")
    print(f"  Tech Stack:")
    print(f"  {'─'*56}")
    print(f"  Build system:    {ts['build_system'] or '(none detected)'}")
    print(f"  Languages:")
    for lang in ts["languages"][:8]:
        print(f"    {lang['name']:<14} {lang['file_count']:>5} files ({lang['percentage']}%)")
    if ts["frameworks"]:
        print(f"  Frameworks:      {', '.join(ts['frameworks'])}")
    if ts["test_frameworks"]:
        print(f"  Test frameworks: {', '.join(ts['test_frameworks'])}")

    if result["entry_points"]:
        print(f"\n  {'─'*56}")
        print(f"  Entry Points ({len(result['entry_points'])}):")
        print(f"  {'─'*56}")
        for ep in result["entry_points"]:
            print(f"  [{ep['type']:9s}] {ep['path']}  ({ep['language']})")

    if result["modules"]:
        print(f"\n  {'─'*56}")
        print(f"  Modules ({len(result['modules'])}):")
        print(f"  {'─'*56}")
        print(f"  {'module':<28} {'files':>5} {'fan_in':>7} {'fan_out':>8}")
        for m in result["modules"][:25]:
            print(f"  {m['name']:<28} {m['files']:>5} {m['fan_in']:>7} {m['fan_out']:>8}")
        if len(result["modules"]) > 25:
            print(f"  ... and {len(result['modules']) - 25} more")

    if result["architecture_docs"]:
        print(f"\n  {'─'*56}")
        print(f"  Architecture Docs ({len(result['architecture_docs'])}):")
        print(f"  {'─'*56}")
        for d in result["architecture_docs"]:
            desc = d["description"][:40] if d["description"] else ""
            print(f"  {d['name']:<20} {d['path']:<24} {desc}")

    print(f"\n{'='*60}\n")


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="arch-optimize: Architecture Scanner (Stage 1 - Architecture Perception)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --target .
  %(prog)s --target src/ --json
  %(prog)s --target . --depth 3
        """,
    )
    parser.add_argument("--target", required=True, help="Project directory to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--depth", type=int, default=5, help="Maximum scan depth (default: 5)")

    args = parser.parse_args()

    if not os.path.isdir(args.target):
        print(f"Error: '{args.target}' is not a directory", file=sys.stderr)
        sys.exit(1)

    result = scan_project(args.target, args.depth)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_human_readable(result)


if __name__ == "__main__":
    main()
