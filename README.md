# arch-optimize

Architecture optimization skill: six decay risk scanning (R1-R6), architect-programmer dual-agent collaboration, and quantitative regression guarding. 5 stdlib-only Python scripts, zero external dependencies.

## Overview

`arch-optimize` delivers a workflow from **architecture analysis** through **incremental optimization** to **regression guarding**:

1. **Six Decay Risk Scanning** (brooks-lint, based on 12 classic engineering books): structured R1-R6 diagnosis with Symptom -> Source -> Consequence -> Remedy findings
2. **Architect-Programmer Dual-Agent Collaboration**: strategy (architect) separated from execution (programmer)
3. **Quantitative Regression Guarding**: asymmetric scoring; quality drops are penalized more than gains are rewarded

## Script Tools

All scripts use Python 3.8+ standard library only (zero external dependencies) and output structured JSON.

| Script | Stage | Function |
|--------|-------|----------|
| `scripts/arch_scan.py` | 1 | Directory scanning, entry point detection, tech stack identification |
| `scripts/dep_graph.py` | 1 | Dependency graph (Mermaid/DOT), circular dependency detection |
| `scripts/risk_diagnose.py` | 2 | R1-R6 six decay risk scanning, four-part findings |
| `scripts/quality_metrics.py` | 3 | MI/CC/HV/Health Score calculation, hotspot identification |
| `scripts/regression_guard.py` | 5 | Test baseline recording, regression comparison |

## Six Decay Risks (R1-R6)

| Risk | Critical Threshold |
|------|--------------------|
| R1 Cognitive Overload | function >50 lines; nesting >5 levels |
| R2 Change Propagation | change touches >5 files |
| R3 Knowledge Duplication | same decision repeated across 3+ modules |
| R4 Accidental Complexity | cyclomatic complexity >15 |
| R5 Dependency Disorder | circular dependency exists |
| R6 Domain Model Distortion | anemic domain model |

False-positive protection (composition-root wiring is not DIP violation, DTOs are not anemic models, etc.) lives in [`references/architecture-principles.md`](references/architecture-principles.md).

## Installation

Requires Python 3.8+ only. No dependencies to install.

```bash
git clone https://github.com/bfxh/arch-optimize.git
cd arch-optimize
python scripts/risk_diagnose.py --target ./src --json
```

Optional: `pip install -e .` installs a metadata-only package (`pyproject.toml` declares no runtime dependencies); use `pip install -e .[dev]` to also get pytest.

## Testing

```bash
python tests/test_smoke.py    # zero-dependency smoke tests (standalone)
pytest                        # same suite via pytest, if installed
```

The suite builds a sample two-package project, runs all five scripts against it, validates JSON schemas, checks determinism, and does a record→compare regression roundtrip.

## Self-Scan Note

Running these tools on this repository itself reports a low health score: `risk_diagnose.py` is a ~1,100-line single-file scanner with intentionally dense dispatch functions. The scanners target production codebases, not skill packages bundled with scripts-as-data. Treat self-scan results as demo output, not a quality claim about your project.

## Usage

```bash
# Stage 1: architecture perception
python3 scripts/arch_scan.py --target ./src --json
python3 scripts/dep_graph.py --target ./src --json

# Stage 2: risk diagnosis
python3 scripts/risk_diagnose.py --target ./src --json
python3 scripts/risk_diagnose.py --target ./src --risk R5 --min-severity Critical --json

# Stage 3: quality metrics
python3 scripts/quality_metrics.py --target ./src --json
python3 scripts/quality_metrics.py --file src/main.py --json

# Stage 5: regression guard
python3 scripts/regression_guard.py record --output baseline.json
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json
```

Typical agent pipeline: arch_scan → dep_graph → risk_diagnose → quality_metrics → regression_guard, passing each stage's JSON as context to the next.

## Supported Languages

Python (.py via ast), Go, C/C++, Rust, TypeScript/JavaScript — import parsing, CC calculation, and function extraction for each.

## Quality Gate Rules

| Gate | Threshold | Type | Failure Behavior |
|------|-----------|------|------------------|
| Zero regression rate | = 100% | Hard | Block PR merge |
| Health score | >= 70 | Soft | Warning + manual approval |
| New code MI | >= 15 | Hard | Block PR merge |
| Cyclomatic complexity | <= 15 | Hard | Block PR merge |
| Circular dependencies | = 0 | Hard | Block PR merge |

## Design Principles

1. **Diagnosis before fix**: never propose fixes before completing risk diagnosis
2. **Incremental over large-scale**: at most 5 improvement requirements per iteration
3. **Zero regression tolerance**: breaking existing functionality costs more than adding features
4. **Division of labor over omniscience**: architect handles strategy, programmer handles execution
5. **Quantitative over intuitive**: MI and health score provide objective baselines
6. **False positive protection**: avoid misclassifying normal design pattern usage as violations
7. **Executable over pure documentation**: every rule has a corresponding script implementation

## Project Structure

```
arch-optimize/
├── SKILL.md                          # Skill definition and workflow documentation
├── README.md
├── LICENSE                           # MIT License
├── pyproject.toml                    # Metadata only, no runtime deps
├── scripts/
│   ├── arch_scan.py                  # Stage 1: architecture perception
│   ├── dep_graph.py                  # Stage 1: dependency graph + cycle detection
│   ├── risk_diagnose.py              # Stage 2: R1-R6 diagnosis
│   ├── quality_metrics.py            # Stage 3: MI/CC/HV/health score
│   └── regression_guard.py           # Stage 5: baseline record & compare
└── references/                       # Load on demand per SKILL.md index
    ├── architecture-principles.md    # Clean Architecture, SOLID thresholds, R1-R6 detail
    ├── coding-conventions.md         # C/C++/Rust/Go/TypeScript conventions
    ├── quality-metrics.md            # MI formula details, Pain×Spread debt ranking
    ├── regression-guard.md           # Zero regression rate, asymmetric scoring
    └── collaboration-workflow.md     # Architect-programmer dual-agent workflow
```

## Companion Skills

Split out of this repo into standalone skills:

- **anti-ai-flavor**: AI-flavor detection for code and docs (`detect_code_ai.py`, `detect_text_ai.py`, 18-pattern catalog)
- **vuln-hunting**: local security scanning and hardening (`vuln-scan.ps1`, `wf.ps1`)
- **project-launcher**: meta-orchestration skill for starting any project

## License

MIT License. See [LICENSE](LICENSE) for details.

## 捐赠支持 (Donate)

如果这个项目对你有帮助，可以请我喝杯咖啡 ☕ 感谢支持！

![donate-qr-wechat](assets/donate-qr-wechat.jpg)

你也可以看看我的 [unified-rx-mcp](https://github.com/bfxh/unified-rx-mcp)。
