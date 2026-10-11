# arch-optimize

Architecture optimization skill: a design-review layer (what a design problem *is*), six decay risk scanning (R1-R6), architect-programmer dual-agent collaboration, and quantitative regression guarding. 5 stdlib-only Python scripts, zero external dependencies.

## Overview

`arch-optimize` delivers a workflow from **design judgement** through **architecture analysis** and **incremental optimization** to **regression guarding**:

1. **Design Review Layer (Stage Zero)**: seven classes of design problem + a five-part finding contract, answered by reading code and git history **before** running any script — [`references/design-review.md`](references/design-review.md)
2. **Six Decay Risk Scanning** (brooks-lint, based on 12 classic engineering books): structured R1-R6 diagnosis with Symptom -> Source -> Consequence -> Remedy findings. These are **lead generators, not conclusions.**
3. **Architect-Programmer Dual-Agent Collaboration**: strategy (architect) separated from execution (programmer)
4. **Quantitative Regression Guarding**: asymmetric scoring; quality drops are penalized more than gains are rewarded

> The split matters: design problems (where a boundary is drawn, who owns an invariant, whether an abstraction is in the right place) have no mechanical criterion, so no script in this repo detects them. A high health score therefore means "no threshold tripped", not "the design is fine" — and the heaviest design problems usually produce **zero findings** here.

## Script Tools

All scripts use Python 3.10+ standard library only (zero external dependencies; CI matrix tests 3.10, 3.12 and 3.13) and output structured JSON.

| Script | Stage | Function |
|--------|-------|----------|
| `scripts/arch_scan.py` | 1 | Directory scanning, entry point detection, tech stack identification |
| `scripts/dep_graph.py` | 1 | Dependency graph (Mermaid/DOT), circular dependency detection |
| `scripts/risk_diagnose.py` | 2 | R1-R6 six decay risk scanning, four-part findings |
| `scripts/quality_metrics.py` | 3 | MI/CC/HV/Health Score calculation, hotspot identification |
| `scripts/regression_guard.py` | 5 | Test baseline recording, regression comparison (incl. vanished tests) |

## Six Decay Risks (R1-R6)

| Risk | Concept | What the script actually asserts |
|------|---------|----------------------------------|
| R1 Cognitive Overload | understanding cost | function >50 lines, nesting >5, **CC >15** = Critical; 20–50 lines / 4–5 nesting = Warning; params >4 = Warning |
| R2 Change Propagation | one change hits many places | per-file import fan-out: >7 Critical, ≥5 Warning (not git co-change count) |
| R3 Knowledge Duplication | one decision expressed twice | 8-gram Jaccard ≥0.6/≥0.8 within the **same top-level directory**; 2+-digit literals repeated ≥3 times across ≥2 files = Critical |
| R4 Accidental Complexity | code harder than the problem | **CC >20** = Critical (Warning on algorithmic paths); abstraction with a single implementation *in the same file* = Warning |
| R5 Dependency Disorder | dependencies point one way | file-level cycles = Critical; domain importing a module that matches an infrastructure marker (word-boundary, `sqlalchemy`-style compounds listed explicitly) = Critical; inner depending on outer = Critical |
| R6 Domain Model Distortion | code mirrors the domain | generic directory name = Warning; cross-context keyword = Warning; Python class whose public surface is only accessors = Warning, field-only class = Suggestion |

Thresholds and every known blind spot (relative imports not graphed, `@dataclass` never flagged as anemic, cross-context duplication reported as Warning only — scaffolding vs domain vocabulary cannot be separated, non-Python CC still a regex approximation over comments/strings, `pub`/`export` leaking into Rust/TS finding names) are listed in [`references/architecture-principles.md`](references/architecture-principles.md) §四 "脚本实测口径". **An empty result from a scanner is not evidence of absence.**

False-positive protection (composition-root wiring is not DIP violation, DTOs are not anemic models, etc.) lives in [`references/architecture-principles.md`](references/architecture-principles.md).

## Design Problems (Stage Zero)

Stage Zero runs **before** the scripts. Seven classes, each reduced to one question you can actually answer against this repo:

| Class | The question |
|-------|--------------|
| Change boundaries | Which unrelated directories did the last real requirement touch? |
| Coupling direction and strength | If B changes, must A change too — and which part of B does A actually use? |
| Abstraction level and location | How many real callers does this abstraction have? How many files does adding a second implementation hit? |
| Invariant ownership | If this rule is bypassed, which line blows up, and who notices first? |
| Evolvability / reversibility | To replace X in six months, how many files move, and which test goes red? |
| Concept -> code fidelity | The word product uses — how many names does it have in code, and are they the same thing? |
| Consistency / single source of truth | When this value or contract changes, how many places must you remember to edit? |

Every design finding must be written as five parts, none optional: **the decision (naming the file/symbol) -> its cost and its benefit -> the evidence I bet it is wrong on -> what happens if change X lands -> why the scripts cannot see it.** Severity comes from how soon X arrives, not from a score. Findings like "N violations found" or "consider refactoring" are rejected by contract: they carry no decision, no cost, no condition.

Full definitions, evidence-gathering steps, per-class explanations of why the scanners stay silent, and the case for *not* reporting a design problem: [`references/design-review.md`](references/design-review.md).

## Installation

Requires Python 3.10+ only. No dependencies to install.

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

The suite builds a sample two-package project, runs all five scripts against it, asserts that each JSON payload contains the expected keys (plus one `pkg_a -> pkg_b` edge), checks that `risk_diagnose` output is deterministic, verifies that a real `pass -> fail` is reported as a regression and that `compare` exits non-zero for it, fails loudly when `record` fails instead of skipping, and pins the documented CLI surface: every flag used in `SKILL.md`/`README.md` must exist in the corresponding script's argparse, and references to non-existent helper scripts or to an untested Python version make the run fail. It also pins the design layer: `references/design-review.md` must exist with all seven problem classes and the five-part finding contract, SKILL.md must keep Stage Zero plus the "lead generator" framing, and no file under `references/` may stay un-indexed.

Detectors that do have a firing fixture: R1 (long/nested functions, via the density and self-scan checks), R3 cross-context downgrade, R5 infrastructure word-boundary, R6 anemic two-tier, and the CC boolean-operator count. Deliberately still uncovered: no fixture asserts R2's fan-out thresholds or R4's single-implementation check fire on known-bad code, and the fixture keeps both packages at the repository root — the one layout that hides `dep_graph`'s `src/` collapse. Those blind spots are documented instead (SKILL.md 「已知限制」) rather than silently asserted-away.

## Self-Scan Note

Running these tools on this repository itself reports poor numbers: over `scripts/` the average MI is about 23, and all five scanners sit below the 15 gate (0.6–11.1) — the only file clearing it is the two-line `__init__.py`. Both scorers return health 0, `risk_diagnose` from 30 Critical + 45 Warning and `quality_metrics` from 10 Critical + 9 Warning. These figures move every time the scanners themselves change length: the pure-reformat commit alone took `risk_diagnose.py` from MI 3.46 to 0.62 without touching a single logic change, which is precisely the artifact being illustrated — MI here is computed per whole file and dominated by the `16.2·ln(LOC)` term, the health score subtracts a flat 15 per finding with no normalization by code volume (`health_score` now also reports `scanned_lines` and `penalty_per_kloc` so cross-project comparison has an anchor; `score` itself stays absolute so the gate contract is unchanged), and the two scorers run different detectors over different file sets, hence different inputs for the same directory. The four numbers above are pinned by `_check_self_scan_claims()` in the smoke suite, so if they drift the run fails and the paragraph must be updated rather than silently going stale.

The scanners target production codebases, not skill packages bundled with scripts-as-data. Treat self-scan results as demo output, not a quality claim about your project.

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
python3 scripts/regression_guard.py record --output baseline.json --test-cmd "python -m pytest -v"
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json
# 有意的测试删除要逐条放行，否则会判红（见 Quality Gate Rules 下）
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json \
    --allow-removed test_removed_on_purpose
```

Typical agent pipeline: stage zero design judgement (questions + evidence, no script) → arch_scan → dep_graph → risk_diagnose → quality_metrics → regression_guard, passing each stage's JSON as context to the next. Scripts narrow the suspicion; they do not close it.

Two caveats when chaining them: `arch_scan` embeds a `scan_timestamp`, so two runs are byte-different across a second boundary and must not be diffed naively; `dep_graph` treats the first directory level under `--target` as a module, so pointing it at a repository root with a `src/` layout collapses every file into one `src` node and yields an empty graph — point it at the module root instead.

## Supported Languages

Python (.py via `ast`), Go, C/C++, Rust, TypeScript/JavaScript — import parsing, CC calculation, and function extraction for each.

For non-Python languages, CC and function extents still come from regex plus brace counting: comments and string literals pollute brace matching, and `switch`/`match` counts both the construct and its case arms. Boolean operators (`&&`, `||`), the ternary `?` and Rust `=>` arms **are** counted now — they used to be wrapped in a `\b(...)\b` group where punctuation can never match, which silently under-counted CC (an `if` with seven `&&` reported 2 instead of 9). Treat these numbers as hints, not verdicts.

## Quality Gate Rules

| Gate | Threshold | Type | Failure Behavior |
|------|-----------|------|------------------|
| Zero regression rate | = 100% | Hard | Block PR merge |
| Health score | >= 70 | Soft | Warning + manual approval |
| New code MI | >= 15 | Hard | Block PR merge |
| Cyclomatic complexity | <= 15 | Hard | Block PR merge (Python only; see Supported Languages) |
| Circular dependencies | = 0 | Hard | Block PR merge |

Only the regression gate is enforceable straight from an exit code, and it now covers both failure modes: a previously-passing test failing **and** a previously-passing test disappearing (delete, rename, skip, or an emptied suite) — the latter fails unless each name is allow-listed with `--allow-removed` / `--allow-removed-file`. Deleting a test that was already failing is allowed. A runnable workflow using only the scripts in this repo is in [`references/regression-guard.md`](references/regression-guard.md) §5.1.

## Design Principles

1. **Diagnosis before fix**: never propose fixes before completing risk diagnosis
2. **Incremental over large-scale**: at most 5 improvement requirements per iteration
3. **Zero regression tolerance**: breaking existing functionality costs more than adding features
4. **Division of labor over omniscience**: architect handles strategy, programmer handles execution
5. **Quantitative as evidence, not verdict**: MI and health score are repeatable baselines for the *same* scope over time; they are heuristic proxies, and architecture-level judgement (layering, boundaries, whether an abstraction earns its keep) stays with the reader
6. **False positive protection**: avoid misclassifying normal design pattern usage as violations — note that several guards suppress real findings too (see §四 of architecture-principles.md), so absence of a finding is not absence of a problem
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
└── references/                       # 7 docs, load on demand per SKILL.md index
    ├── design-review.md              # Stage 0: seven classes of design problem + five-part finding contract
    ├── architecture-principles.md    # Clean Architecture, SOLID thresholds, R1-R6 detail + measured script caliber
    ├── coding-conventions.md         # C/C++/Rust/Go/TypeScript conventions
    ├── quality-metrics.md            # MI formula details, tech debt Pain×Spread ranking
    ├── regression-guard.md           # Zero regression rate, asymmetric scoring, CI gate
    ├── collaboration-workflow.md     # Architect-programmer dual-agent workflow
    └── engineering-responsibility.md # Root philosophy, src/bin project layout rules
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
