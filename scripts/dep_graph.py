#!/usr/bin/env python3
"""arch-optimize: Dependency Graph Generator

Generates Mermaid/Graphviz dependency graphs from source code imports.
Detects circular dependencies and calculates fan-in/fan-out metrics.

Supports: Python, Go, C/C++, Rust, TypeScript/JavaScript
Dependencies: Python 3.8+ stdlib only

Usage:
    python3 dep_graph.py --target src/ --format mermaid
    python3 dep_graph.py --target . --json
    python3 dep_graph.py --target src/ --output graph.md --format mermaid
    python3 dep_graph.py --target . --max-depth 3 --format dot
"""

import argparse
import ast
import json
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
}

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "__pycache__", ".cache",
    "dist", "build", "target", ".venv", "venv", "env",
    ".idea", ".vscode", "coverage", ".next", ".nuxt",
}

LAYER_KEYWORDS = {
    "domain": {"domain", "model", "entity", "models", "entities"},
    "application": {"application", "service", "services", "usecase", "usecases", "app"},
    "infrastructure": {"infrastructure", "infra", "repository", "repositories",
                       "db", "database", "persistence", "store", "storage"},
    "presentation": {"presentation", "api", "controller", "controllers",
                     "handler", "handlers", "web", "ui", "view", "views",
                     "router", "routers", "endpoint", "endpoints"},
}

# ── Regex patterns ──────────────────────────────────────────────────

GO_IMPORT_SINGLE_RE = re.compile(r'^import\s+"([^"]+)"', re.MULTILINE)
GO_IMPORT_BLOCK_RE = re.compile(r'import\s*\(\s*(.*?)\s*\)', re.DOTALL)
GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
C_INCLUDE_LOCAL_RE = re.compile(r'#include\s*"([^"]+)"')
RUST_USE_RE = re.compile(r'^\s*(pub\s+)?use\s+([\w:]+)', re.MULTILINE)
RUST_MOD_RE = re.compile(r'^\s*(pub\s+)?mod\s+(\w+)', re.MULTILINE)
TS_IMPORT_RE = re.compile(
    r'(?:import\s+[^;]*?\s+from\s+|import\s+|require\s*\(\s*)["\']([^"\']+)["\']')

# ── Import parsers ──────────────────────────────────────────────────

def parse_python_imports(filepath: str, target: str) -> list:
    """Parse Python imports using ast, returning top-level module names."""
    imports = []
    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            tree = ast.parse(f.read(), filename=filepath)
    except Exception:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imports.append(node.module.split(".")[0])
            else:
                parts = Path(os.path.relpath(filepath, target)).parts[:-1]
                if node.level <= len(parts):
                    base = list(parts[: len(parts) - (node.level - 1)])
                else:
                    base = []
                if node.module:
                    base += node.module.split(".")
                if base:
                    imports.append(base[0])
    return imports


def parse_go_imports(source: str) -> list:
    """Parse Go import statements, returning import paths."""
    imports = [m.group(1) for m in GO_IMPORT_SINGLE_RE.finditer(source)]
    for block in GO_IMPORT_BLOCK_RE.finditer(source):
        for line in block.group(1).split("\n"):
            line = line.strip()
            if line and not line.startswith("//"):
                m = GO_IMPORT_LINE_RE.search(line)
                if m:
                    imports.append(m.group(1))
    return imports


def parse_rust_imports(source: str) -> list:
    """Parse Rust use/mod statements, returning (type, name) tuples."""
    imports = []
    for m in RUST_USE_RE.finditer(source):
        parts = m.group(2).rstrip(":").split("::")
        if parts[0] == "crate" and len(parts) > 1:
            imports.append(("internal", parts[1]))
        elif parts[0] != "crate":
            imports.append(("external", parts[0]))
    for m in RUST_MOD_RE.finditer(source):
        imports.append(("internal", m.group(2)))
    return imports


def parse_ts_js_imports(source: str, filepath: str, target: str) -> list:
    """Parse TS/JS import/require, returning (type, name) tuples."""
    imports = []
    for m in TS_IMPORT_RE.finditer(source):
        path = m.group(1)
        if path.startswith("."):
            resolved = os.path.normpath(
                os.path.join(os.path.dirname(filepath), path))
            try:
                rel = os.path.relpath(resolved, target)
            except ValueError:
                continue
            if rel.startswith(".."):
                continue
            parts = Path(rel).parts
            if parts and parts[0] != ".":
                imports.append(("internal", parts[0]))
        elif path.startswith("/"):
            parts = Path(path).parts[1:]
            if parts:
                imports.append(("internal", parts[0]))
    return imports


# ── Module resolution ───────────────────────────────────────────────

def file_to_module(filepath: str, target: str) -> str:
    """Map a file path to its top-level module name."""
    parts = Path(os.path.relpath(filepath, target)).parts
    return Path(parts[0]).stem if len(parts) == 1 else parts[0]


def detect_layer(name: str) -> str:
    """Detect the architectural layer of a module by name."""
    lower = name.lower()
    for layer, keywords in LAYER_KEYWORDS.items():
        if lower in keywords:
            return layer
    return None


def find_go_module_path(target: str) -> str:
    """Find the Go module path from go.mod if present."""
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        if "go.mod" in files:
            try:
                with open(os.path.join(root, "go.mod"), "r",
                          encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        if line.strip().startswith("module "):
                            return line.strip().split()[1]
            except Exception:
                pass
    return None


def map_go_import(import_path: str, module_path: str, local_dirs: set) -> str:
    """Map a Go import path to a module name, or None if external."""
    first = import_path.split("/")[0]
    if "." not in first:
        return None  # standard library
    if module_path:
        if import_path == module_path:
            return None
        if import_path.startswith(module_path + "/"):
            return import_path[len(module_path) + 1:].split("/")[0]
    for seg in import_path.split("/"):
        if seg in local_dirs:
            return seg
    return None  # third-party


# ── Graph construction ──────────────────────────────────────────────

def build_dependency_graph(target: str, max_depth: int = 0) -> tuple:
    """Build a dependency graph from source files under target."""
    target = os.path.abspath(target)
    adj, modules = {}, {}
    go_module_path = find_go_module_path(target)
    local_go_dirs = set()

    # First pass: collect files and local modules
    file_list = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        if max_depth > 0:
            if len(Path(root).relative_to(target).parts) > max_depth:
                dirs[:] = []
                continue
        for fname in sorted(files):
            ext = Path(fname).suffix.lower()
            if ext not in LANG_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            file_list.append(fpath)
            mod = file_to_module(fpath, target)
            if mod not in modules:
                modules[mod] = {"layer": detect_layer(mod), "files": 0}
                adj[mod] = set()
            modules[mod]["files"] += 1
            if ext == ".go":
                rel_root = Path(root).relative_to(target)
                if rel_root.parts:
                    local_go_dirs.add(rel_root.parts[0])

    # Second pass: parse imports and build edges
    for fpath in file_list:
        ext = Path(fpath).suffix.lower()
        lang = LANG_EXTENSIONS[ext]
        src_mod = file_to_module(fpath, target)
        try:
            with open(fpath, "r", encoding="utf-8-sig", errors="replace") as f:
                source = f.read()
        except Exception:
            continue

        new_deps = set()
        if lang == "python":
            for imp in parse_python_imports(fpath, target):
                if imp in modules and imp != src_mod:
                    new_deps.add(imp)
        elif lang == "go":
            for imp in parse_go_imports(source):
                mapped = map_go_import(imp, go_module_path, local_go_dirs)
                if mapped and mapped in modules and mapped != src_mod:
                    new_deps.add(mapped)
        elif lang in ("c", "cpp"):
            for inc in [m.group(1) for m in C_INCLUDE_LOCAL_RE.finditer(source)]:
                parts = Path(inc).parts
                if len(parts) > 1 and parts[0] in modules and parts[0] != src_mod:
                    new_deps.add(parts[0])
        elif lang == "rust":
            for typ, name in parse_rust_imports(source):
                if typ == "internal" and name in modules and name != src_mod:
                    new_deps.add(name)
        elif lang in ("typescript", "javascript"):
            for typ, name in parse_ts_js_imports(source, fpath, target):
                if typ == "internal" and name in modules and name != src_mod:
                    new_deps.add(name)

        adj[src_mod].update(new_deps)

    return modules, adj


# ── Cycle detection (Tarjan's SCC) ──────────────────────────────────

def find_sccs(nodes: list, adj: dict) -> list:
    """Find strongly connected components using Tarjan's algorithm."""
    idx_counter = [0]
    stack, lowlink, index, on_stack = [], {}, {}, {}
    sccs = []

    def strongconnect(v):
        index[v] = idx_counter[0]
        lowlink[v] = idx_counter[0]
        idx_counter[0] += 1
        stack.append(v)
        on_stack[v] = True
        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w):
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            sccs.append(scc)

    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(nodes) * 2 + 100))
    for v in nodes:
        if v not in index:
            strongconnect(v)
    return sccs


def extract_cycle(scc: list, adj: dict) -> list:
    """Extract a representative cycle path from an SCC."""
    scc_set = set(scc)
    if len(scc) == 1:
        node = scc[0]
        return [node, node] if node in adj.get(node, []) else None
    path, visited = [], set()

    def dfs(v):
        path.append(v)
        visited.add(v)
        for w in adj.get(v, []):
            if w not in scc_set:
                continue
            if w in path:
                return path[path.index(w):] + [w]
            if w not in visited:
                result = dfs(w)
                if result:
                    return result
        path.pop()
        return None

    return dfs(scc[0])


# ── Metrics & output generation ─────────────────────────────────────

def sanitize_id(name: str) -> str:
    """Sanitize a module name for use as a graph node identifier."""
    return re.sub(r"[^\w]", "_", name)


def generate_mermaid(modules: dict, adj: dict, scc_map: dict,
                     scc_size: dict, cycles: list) -> str:
    """Generate a Mermaid graph string."""
    lines = ["graph TD"]
    by_layer, unlayered = {}, []
    for name in sorted(modules):
        layer = modules[name].get("layer")
        if layer:
            by_layer.setdefault(layer, []).append(name)
        else:
            unlayered.append(name)
    for layer in ["domain", "application", "infrastructure", "presentation"]:
        if layer in by_layer:
            lines.append(f"    subgraph {layer.capitalize()}")
            for name in by_layer[layer]:
                lines.append(f"        {sanitize_id(name)}")
            lines.append("    end")
    for name in unlayered:
        lines.append(f"    {sanitize_id(name)}")
    for src in sorted(adj):
        for dst in sorted(adj[src]):
            is_circ = (scc_map.get(src) is not None
                       and scc_map.get(src) == scc_map.get(dst)
                       and scc_size.get(scc_map[src], 0) > 1)
            arrow = "-.->" if is_circ else "-->"
            lines.append(f"    {sanitize_id(src)} {arrow} {sanitize_id(dst)}")
    for cycle in cycles:
        lines.append(f"    %% Circular dependency: {' -> '.join(cycle)}")
    return "\n".join(lines)


def generate_dot(modules: dict, adj: dict, scc_map: dict, scc_size: dict) -> str:
    """Generate a Graphviz DOT graph string."""
    lines = ["digraph dependencies {", "    rankdir=LR;",
             "    node [shape=box];", ""]
    for name in sorted(modules):
        lines.append(f'    {sanitize_id(name)} [label="{name}"];')
    lines.append("")
    for src in sorted(adj):
        for dst in sorted(adj[src]):
            is_circ = (scc_map.get(src) is not None
                       and scc_map.get(src) == scc_map.get(dst)
                       and scc_size.get(scc_map[src], 0) > 1)
            suffix = " [style=dashed]" if is_circ else ""
            lines.append(f"    {sanitize_id(src)} -> {sanitize_id(dst)}{suffix};")
    lines.append("}")
    return "\n".join(lines)


def build_result(target: str, modules: dict, adj: dict) -> dict:
    """Build the complete result dictionary with all graph data."""
    fan_in = {m: 0 for m in modules}
    fan_out = {m: len(adj.get(m, set())) for m in modules}
    for src, deps in adj.items():
        for dst in deps:
            if dst in fan_in:
                fan_in[dst] += 1

    sccs = find_sccs(list(modules.keys()), adj)
    scc_map, scc_size = {}, {}
    for i, scc in enumerate(sccs):
        for node in scc:
            scc_map[node] = i
        scc_size[i] = len(scc)

    cycles = []
    for scc in sccs:
        cycle = extract_cycle(scc, adj)
        if cycle:
            cycles.append(cycle)

    edges = []
    for src in sorted(adj):
        for dst in sorted(adj[src]):
            is_circ = (scc_map.get(src) is not None
                       and scc_map.get(src) == scc_map.get(dst)
                       and scc_size.get(scc_map[src], 0) > 1)
            edges.append({"from": src, "to": dst,
                          "type": "circular" if is_circ else "normal"})

    module_list = [{
        "name": name,
        "fan_in": fan_in.get(name, 0),
        "fan_out": fan_out.get(name, 0),
        "layer": modules[name].get("layer"),
        "files": modules[name].get("files", 0),
    } for name in sorted(modules)]

    return {
        "target": target,
        "modules": module_list,
        "edges": edges,
        "circular_deps": cycles,
        "mermaid": generate_mermaid(modules, adj, scc_map, scc_size, cycles),
        "dot": generate_dot(modules, adj, scc_map, scc_size),
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="arch-optimize: Dependency Graph Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --target src/ --format mermaid
  %(prog)s --target . --json
  %(prog)s --target src/ --output graph.md --format mermaid
  %(prog)s --target . --max-depth 3 --format dot
        """,
    )
    parser.add_argument("--target", required=True, help="Source directory to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", help="Write output to file (.md, .gv, .dot, .json)")
    parser.add_argument("--format", choices=["mermaid", "dot"], default="mermaid",
                        help="Graph format (default: mermaid)")
    parser.add_argument("--max-depth", type=int, default=0,
                        help="Maximum directory depth to scan (0 = unlimited)")

    args = parser.parse_args()

    if not os.path.isdir(args.target):
        print(f"Error: {args.target} is not a directory", file=sys.stderr)
        sys.exit(1)

    modules, adj = build_dependency_graph(args.target, args.max_depth)
    if not modules:
        print("Error: No analyzable source files found", file=sys.stderr)
        sys.exit(1)

    result = build_result(args.target, modules, adj)
    graph_str = result["mermaid"] if args.format == "mermaid" else result["dot"]

    if args.json:
        output = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"JSON written to {args.output}", file=sys.stderr)
        else:
            print(output)
        return

    # Human-readable output
    print(f"\n{'='*60}")
    print(f"  arch-optimize Dependency Graph")
    print(f"{'='*60}")
    print(f"  Target:              {result['target']}")
    print(f"  Modules:             {len(result['modules'])}")
    print(f"  Edges:               {len(result['edges'])}")
    print(f"  Circular deps:       {len(result['circular_deps'])}")

    print(f"\n  {'─'*56}")
    print(f"  Modules (fan-in / fan-out):")
    print(f"  {'─'*56}")
    for m in result["modules"]:
        layer = f" [{m['layer']}]" if m["layer"] else ""
        print(f"  {m['name']:30s}  in={m['fan_in']:3d}  out={m['fan_out']:3d}{layer}")

    print(f"\n  {'─'*56}")
    print(f"  {args.format.upper()} Graph:")
    print(f"  {'─'*56}")
    print(f"  ```{args.format}")
    for line in graph_str.split("\n"):
        print(f"  {line}")
    print(f"  ```")

    if result["circular_deps"]:
        print(f"\n  {'─'*56}")
        print(f"  Circular Dependencies ({len(result['circular_deps'])}):")
        print(f"  {'─'*56}")
        for i, cycle in enumerate(result["circular_deps"], 1):
            print(f"  {i}. {' -> '.join(cycle)}")

    print(f"\n{'='*60}\n")

    # Write to file
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                if args.output.endswith(".md"):
                    f.write("# Dependency Graph\n\n")
                    f.write(f"```{args.format}\n{graph_str}\n```\n")
                    if result["circular_deps"]:
                        f.write("\n## Circular Dependencies\n\n")
                        for i, cycle in enumerate(result["circular_deps"], 1):
                            f.write(f"{i}. {' -> '.join(cycle)}\n")
                else:
                    f.write(graph_str + "\n")
            print(f"Graph written to {args.output}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing file: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
