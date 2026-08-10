# arch-optimize

Architecture optimization skill: six decay risk scanning (R1-R6), architect-programmer dual-agent collaboration, anti-AI-flavor detection, and a local script toolkit. Provides coding conventions, quality metrics, and regression guarding for AI-driven code review and refactoring workflows.

## Overview

`arch-optimize` delivers a complete workflow from **architecture analysis** through **incremental optimization** to **regression guarding**:

1. **Six Decay Risk Scanning** (brooks-lint, based on 12 classic engineering books): Structured R1-R6 diagnosis with Symptom -> Source -> Consequence -> Remedy findings
2. **Architect-Programmer Dual-Agent Collaboration**: Separates strategy (architect) from execution (programmer) to avoid the "god's eye view" problem
3. **Anti-AI-Flavor Detection**: 18 AI-specific low-quality patterns (dead code, placeholders, model pride, etc.)

## Script Tools

The project includes 5 executable scripts that turn theoretical formulas and detection rules into runnable code. All scripts use Python 3.8+ standard library only (zero external dependencies) and output structured JSON.

| Script | Stage | Function | Output Format |
|--------|-------|----------|---------------|
| `scripts/arch_scan.py` | Stage 1 | Directory scanning, entry point detection, tech stack identification, document localization | JSON / Human-readable |
| `scripts/dep_graph.py` | Stage 1 | Dependency graph generation (Mermaid/DOT), circular dependency detection | JSON / Mermaid / DOT |
| `scripts/risk_diagnose.py` | Stage 2 | R1-R6 six decay risk scanning with four-part findings | JSON / Human-readable |
| `scripts/quality_metrics.py` | Stage 3 | MI/CC/HV/Health Score calculation, hotspot identification | JSON / Human-readable |
| `scripts/regression_guard.py` | Stage 5 | Test baseline recording, regression comparison | JSON / Human-readable |

## MCP Tools

The Level 3 MCP plugin exposes 5 structured tools via the MCP protocol (FastMCP framework, stdio transport). AI agents can discover and call these tools without parsing CLI usage.

| MCP Tool | Stage | CLI Script | Read-Only | Idempotent |
|----------|-------|------------|-----------|------------|
| `arch_optimize_scan` | Stage 1 | arch_scan.py | Yes | Yes |
| `arch_optimize_dep_graph` | Stage 1 | dep_graph.py | Yes | Yes |
| `arch_optimize_risk_diagnose` | Stage 2 | risk_diagnose.py | Yes | Yes |
| `arch_optimize_quality_metrics` | Stage 3 | quality_metrics.py | Yes | Yes |
| `arch_optimize_regression_guard` | Stage 5 | regression_guard.py | No | No |

### MCP Tool Parameters

**arch_optimize_scan**
- `target` (str, required): Project root directory path
- `depth` (int, default 5): Maximum directory scan depth (1-20)

**arch_optimize_dep_graph**
- `target` (str, required): Source code directory path
- `format` (str, default "mermaid"): Graph format, "mermaid" or "dot"
- `max_depth` (int, default 0): Maximum scan depth, 0 = unlimited

**arch_optimize_risk_diagnose**
- `target` (str, required): Project directory path
- `risk` (str, optional): Filter single risk type "R1"-"R6"
- `min_severity` (str, optional): Minimum severity "Critical"/"Warning"/"Suggestion"

**arch_optimize_quality_metrics**
- `target` (str, optional): Analysis directory (mutually exclusive with `file`)
- `file` (str, optional): Analyze a single file (mutually exclusive with `target`)
- `min_cc` (int, default 0): Only report functions with CC >= this value

**arch_optimize_regression_guard**
- `action` (str, required): Subcommand "record"/"compare"
- `target` (str, record optional): Working directory
- `baseline` (str, compare required): Baseline JSON file
- `current` (str, compare required): Current JSON file
- `test_cmd` (str, record optional): Test command
- `output` (str, record required): Output JSON file path

## Installation

### Prerequisites

- Python 3.10 or higher
- pip or any PEP 517 compatible build backend

### From Source

```bash
git clone https://github.com/your-username/arch-optimize.git
cd arch-optimize
pip install -e .
```

### Dependencies

```
mcp>=1.28.1,<2
pydantic>=2.0.0
```

The 5 analysis scripts (arch_scan, dep_graph, risk_diagnose, quality_metrics, regression_guard) use **Python standard library only** -- no external dependencies required. The MCP server (`mcp_server.py`) requires `mcp` and `pydantic`.

## Usage

### CLI (Level 2)

```bash
# Stage 1: Architecture perception
python3 scripts/arch_scan.py --target ./src --json
python3 scripts/dep_graph.py --target ./src --json

# Stage 2: Risk diagnosis
python3 scripts/risk_diagnose.py --target ./src --json
python3 scripts/risk_diagnose.py --target ./src --risk R5 --json
python3 scripts/risk_diagnose.py --target ./src --min-severity Critical --json

# Stage 3: Quality metrics
python3 scripts/quality_metrics.py --target ./src --json
python3 scripts/quality_metrics.py --file src/main.py --json
python3 scripts/quality_metrics.py --target ./src --min-cc 10

# Stage 5: Regression guard
python3 scripts/regression_guard.py record --output baseline.json
python3 scripts/regression_guard.py record --output current.json
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json
```

### MCP Server (Level 3)

Start the MCP server via stdio transport:

```bash
python3 scripts/mcp_server.py
```

Configure in your MCP client (e.g., Claude Desktop, TRAE, etc.):

```json
{
  "mcpServers": {
    "arch_optimize": {
      "command": "python3",
      "args": ["path/to/arch-optimize/scripts/mcp_server.py"]
    }
  }
}
```

## Supported Languages

| Language | Extensions | Import Parsing | CC Calculation | Function Extraction |
|----------|-----------|----------------|----------------|---------------------|
| Python | .py | ast module | ast traversal | ast.FunctionDef |
| Go | .go | import parsing | regex + brace matching | func keyword |
| C/C++ | .c .h .cpp .hpp | #include parsing | regex + brace matching | function signature matching |
| Rust | .rs | use/mod parsing | regex + brace matching | fn keyword |
| TypeScript | .ts .tsx | import/from parsing | regex + brace matching | function / arrow functions |
| JavaScript | .js .jsx | import/require parsing | regex + brace matching | function / arrow functions |

## Quality Gate Rules

| Gate | Threshold | Type | Failure Behavior |
|------|-----------|------|-----------------|
| Zero regression rate | = 100% | Hard | Block PR merge |
| Health score | >= 70 | Soft | Warning + requires manual approval |
| Release health score | >= 80 | Hard | Block release |
| New code MI | >= 15 | Hard | Block PR merge |
| Cyclomatic complexity | <= 15 | Hard | Block PR merge |
| Circular dependencies | = 0 | Hard | Block PR merge |
| Performance regression | < 10% | Soft | Warning + requires explanation |

## Design Principles

1. **Diagnosis before fix**: Never propose fixes before completing risk diagnosis (brooks-lint iron law)
2. **Incremental over large-scale**: At most 5 improvement requirements per iteration, small steps
3. **Zero regression tolerance**: Breaking existing functionality costs more than adding new features
4. **Division of labor over omniscience**: Architect handles strategy, programmer handles execution, avoiding god's eye view
5. **Quantitative over intuitive**: MI, health score provide objective baselines
6. **False positive protection**: Avoid misclassifying normal design pattern usage as violations
7. **Executable over pure documentation**: All theoretical formulas and detection rules have corresponding script implementations that AI agents can directly call for quantitative data
8. **Protocol over command line**: MCP plugin encapsulation enables tools to be discovered and called by any AI agent via standard protocol without parsing CLI usage

## Project Structure

```
arch-optimize/
├── SKILL.md                          # Skill definition and workflow documentation
├── README.md                         # This file
├── LICENSE                           # MIT License
├── .gitignore                        # Python gitignore
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Python project configuration
├── scripts/
│   ├── arch_scan.py                  # Stage 1: Architecture perception
│   ├── dep_graph.py                  # Stage 1: Dependency graph
│   ├── risk_diagnose.py              # Stage 2: R1-R6 risk diagnosis
│   ├── quality_metrics.py            # Stage 3: Quality metrics
│   ├── regression_guard.py           # Stage 5: Regression guard
│   └── mcp_server.py                 # MCP server (Level 3)
├── references/
│   ├── architecture-principles.md    # Clean Architecture, SOLID, DDD, R1-R6
│   ├── coding-conventions.md         # C/C++/Rust/Go/TypeScript conventions
│   ├── quality-metrics.md            # MI, health score, SQALE
│   ├── regression-guard.md           # Zero regression rate, asymmetric scoring
│   └── collaboration-workflow.md     # Architect-programmer collaboration
└── evaluations/
    └── evaluation.xml                # 12 QA pairs for MCP tool evaluation
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## 捐赠支持 (Donate)

如果这个项目对你有帮助，可以请我喝杯咖啡 ☕ 感谢支持！<img width="1263" height="1719" alt="302faffd53d00640514e0264113c1158" src="https://github.com/user-attachments/assets/234bb1b1-5abb-46d1-8f58-706b5ca81b96" />
然后就是可以看看我的https://github.com/bfxh/unified-rx-mcp 主要是skill还是有好多的局限的

If this project helps you, feel free to buy me a coffee ☕ Thanks for your support!


