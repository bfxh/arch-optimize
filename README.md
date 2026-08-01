# arch-optimize

Architecture optimization skill that fuses SWE-CI evolutionary quality assessment, six decay risk scanning, and architect-programmer dual-agent collaboration into a single toolkit. Provides coding conventions, quality metrics, and regression guarding for AI-driven code review and refactoring workflows.

## Overview

`arch-optimize` integrates three theoretical frameworks to deliver a complete workflow from **architecture analysis** through **incremental optimization** to **regression guarding**:

1. **SWE-CI Evolutionary Quality Assessment** (Sun Yat-sen University + Alibaba): Uses EvoScore to measure long-term code maintainability with asymmetric scoring that penalizes regressions
2. **Six Decay Risk Scanning** (brooks-lint, based on 12 classic engineering books): Structured R1-R6 diagnosis with Symptom -> Source -> Consequence -> Remedy findings
3. **Architect-Programmer Dual-Agent Collaboration**: Separates strategy (architect) from execution (programmer) to avoid the "god's eye view" problem

## Three-Level Evolution Path

| Level | Form | Invocation | Version |
|-------|------|-----------|---------|
| Level 1 | Pure documentation | AI reads docs, then manually analyzes | v1.0 |
| Level 2 | Script-enhanced | CLI commands with JSON output | v2.0 |
| Level 3 | MCP plugin | Direct MCP protocol calls with structured tools | v3.0 |

## Script Tools

The project includes 5 executable scripts that turn theoretical formulas and detection rules into runnable code. All scripts use Python 3.8+ standard library only (zero external dependencies) and output structured JSON.

| Script | Stage | Function | Output Format |
|--------|-------|----------|---------------|
| `scripts/arch_scan.py` | Stage 1 | Directory scanning, entry point detection, tech stack identification, document localization | JSON / Human-readable |
| `scripts/dep_graph.py` | Stage 1 | Dependency graph generation (Mermaid/DOT), circular dependency detection | JSON / Mermaid / DOT |
| `scripts/risk_diagnose.py` | Stage 2 | R1-R6 six decay risk scanning with four-part findings | JSON / Human-readable |
| `scripts/quality_metrics.py` | Stage 3 | MI/CC/HV/Health Score calculation, hotspot identification | JSON / Human-readable |
| `scripts/regression_guard.py` | Stage 5 | Test baseline recording, regression comparison, EvoScore calculation | JSON / Human-readable |

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
- `action` (str, required): Subcommand "record"/"compare"/"evoscore"
- `target` (str, record optional): Working directory
- `baseline` (str, compare required): Baseline JSON file
- `current` (str, compare required): Current JSON file
- `history` (str, evoscore required): History JSON file
- `gamma` (float, default 1.5): Discount factor
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
python3 scripts/regression_guard.py evoscore --history history.json --gamma 1.5
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

1. **Evolution over snapshot**: Code quality is not a single state but a trajectory over time (SWE-CI core insight)
2. **Diagnosis before fix**: Never propose fixes before completing risk diagnosis (brooks-lint iron law)
3. **Incremental over large-scale**: At most 5 improvement requirements per iteration, small steps (SWE-CI architect mode)
4. **Zero regression tolerance**: Breaking existing functionality costs more than adding new features (EvoScore asymmetric design)
5. **Division of labor over omniscience**: Architect handles strategy, programmer handles execution, avoiding god's eye view (SWE-CI dual-agent)
6. **Quantitative over intuitive**: MI, health score, EvoScore provide objective baselines
7. **False positive protection**: Avoid misclassifying normal design pattern usage as violations
8. **Executable over pure documentation**: All theoretical formulas and detection rules have corresponding script implementations that AI agents can directly call for quantitative data (v2.0 upgrade)
9. **Protocol over command line**: MCP plugin encapsulation enables tools to be discovered and called by any AI agent via standard protocol without parsing CLI usage (v3.0 upgrade)

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
│   ├── quality-metrics.md            # MI, EvoScore, health score, SQALE
│   ├── regression-guard.md           # Zero regression rate, asymmetric scoring
│   └── collaboration-workflow.md     # Architect-programmer collaboration
└── evaluations/
    └── evaluation.xml                # 10 QA pairs for MCP tool evaluation
```

## License

MIT License. See [LICENSE](LICENSE) for details.
