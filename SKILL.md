---
name: "arch-optimize"
description: "架构优化技能 v3.2：六大衰退风险扫描（R1-R6）、质量度量（MI/CC/健康分）、回归防护。五阶段工作流配 5 个零依赖脚本（arch_scan/dep_graph/risk_diagnose/quality_metrics/regression_guard），输出 JSON；脚本只给证据，引用数字前先读「已知限制」。架构审查、技术债评估、代码重构、质量提升、工程结构评审时调用。"
version: "3.2"
runAs: subagent
allowed-tools: read_file, write_file, edit_file, grep, glob, bash
---

# 架构优化技能 v3.2

## 定位

**根哲学：对工程负责。** 交付的每一行代码、每一份文档、每一个决策，都必须经得起工程检验（详见 `references/engineering-responsibility.md`）。

三个核心能力：
1. **六大衰退风险扫描**（brooks-lint，基于 12 本经典工程书籍）：R1-R6 结构化诊断
2. **架构师-程序员双智能体协作**：战略层与执行层分离，避免上帝视角
3. **量化回归防护**：非对称评分惩罚回归，零退化率才可合并

## 调用时机

- 架构审查、技术债评估、代码重构、质量提升、工程结构评审
- 新项目开工（强制 src/ + bin/ 分离）
- 交付前质量门禁（配合 preflight）

## 五阶段工作流

### 阶段一：架构感知（arch_scan + dep_graph）

```bash
python scripts/arch_scan.py --target <项目> --json
python scripts/dep_graph.py --target <项目> --json
```

产出：目录树/文件清单、依赖图（fan_in/fan_out）、模块边界。

**两个脚本的"模块"口径不同，不可互换**：`dep_graph` 把 `--target` 的**下一级目录**当作一个模块，`arch_scan` 把**每个含源文件的目录**当作一个模块。因此 `--target .` 扫一个 `src/ + bin/` 布局的规范项目时，dep_graph 只有 `src`、`bin` 两个节点、边与环为空——这不是"没有依赖"，是指错层级。要得到有意义的图，`--target` 应指向模块根（如 `./src`）。

### 阶段二：风险诊断 R1-R6（risk_diagnose）

```bash
python scripts/risk_diagnose.py --target <项目> --json
```

| 编号 | 风险 | 概念定义 | 脚本实际判据（代码为准） | 脚本量不到的部分 |
|------|------|----------|--------------------------|------------------|
| R1 | 认知过载 | 理解成本 | 函数 >50 行 / 嵌套 >5 层 / CC >15 = Critical；20–50 行、4–5 层 = Warning；参数 >4 = Warning | 语义密度、命名是否揭示意图 |
| R2 | 变更传播 | 改一处波及多处 | 单文件 import 扇出：>7 = Critical，≥5 = Warning | 真实"变更触及 N 文件"需 git 共变历史，脚本未实现 |
| R3 | 知识重复 | 同一决策多处表达 | 8-gram Jaccard ≥0.6 Warning / ≥0.8 Critical；**跨上下文的一律降 Warning 并标明两上下文名**，同上下文按原阈值；≥2 位数字面量重复 ≥3 次且跨 ≥2 文件 = Critical | 纯词汇层面分不出"通用脚手架"与"领域词"，跨上下文报的是可能而非定论 |
| R4 | 偶发复杂性 | 比问题本身更复杂 | CC >20 = Critical（路径含算法关键词降 Warning）；同文件内仅一个实现的抽象类/接口/工厂 = Warning | 跨文件的实现计数；"这个抽象是否必要" |
| R5 | 依赖失序 | 依赖方向一致 | 文件级循环依赖 = Critical；领域层 import 命中 infra 标记（**词边界匹配**，`_`/`-`/`.` 视作边界）= Critical；内层(rank≥2)依赖外层 = Critical | 相对导入 `from . import x` 不建边，包内环检不出；复合名（如 `sqlalchemy`）须在标记表显式登记才认得出 |
| R6 | 领域模型扭曲 | 代码忠实表达问题 | 目录名命中通用技术词 = Warning；跨上下文关键词泄漏 = Warning；Python 类"公开面全是访问器" = Warning、"只有字段无任何方法" = Suggestion | `@dataclass` 纯字段类只给 Suggestion（值对象也长这样）；跨语言不判 |

> **注意 CC 的两个不同阈值**：CC>15 记在 **R1**（认知过载），CC>20 才记 **R4**（偶发复杂性）。二者是两条独立判据，不是同一规则的两种写法。
> 非 Python 语言的 CC 与函数抽取仍是**正则近似**，但布尔运算符 `&&`/`||`、三元 `?`、Rust `=>` 臂**已经计入**（改前被塞进 `\b` 组永远匹配不到：实测 if+7 个 `&&` 真值 9 被算成 2、三元 `?` 真值 2 被算成 1，已修）。剩余近似点：注释与字符串里的括号会污染花括号配对的函数边界，`switch`/`match` 本体与 case 臂都计一次（与仓内 C 口径一致）。这些数字仍只当"提示"。

每条发现四段式：**Symptom → Source → Consequence → Remedy**。
假阳性防护（组合根装配≠DIP 违规、DTO≠贫血模型等）见 `references/architecture-principles.md`。

**铁律：完成风险诊断前，绝不提出修复建议。**

### 阶段三：质量度量（quality_metrics）

```bash
python scripts/quality_metrics.py --target <项目> --json
```

MI / 圈复杂度 CC / 逻辑行 LOC / 健康分 = 100 - 15×Critical - 5×Warning - 1×Suggestion。

口径说明（避免把度量读成结论）：
- MI 按**整文件**计算，`16.2·ln(LOC)` 项主导，因此 MI 随文件长度单调下降——同一风格的代码，332 行的文件可以低于 15 的门而 12 行的文件轻松过线。MI 低首先说明"文件大"，不说明"设计差"。
- 健康分按发现条数的**绝对值**扣分，无规模归一：同一份内容复制 20 份即从 85 分掉到 0 分。跨项目比较健康分没有意义，只对"同一范围、同一口径"的前后两次扫描可比。为此两个计分器现在都多输出两个字段：`scanned_lines`（物理行数，供复算）与 `penalty_per_kloc`（密度制扣分 = 15C+5W+1S × 1000 / 行数）——**跨项目、跨规模只能比 `penalty_per_kloc`**；`score` 刻意保留绝对计数，门禁契约不改。

### 阶段四：增量优化（方法论）

在架构师约束下执行增量改进：每次最多 5 个需求，小步快跑。
完整双智能体流程与需求文档规范见 `references/collaboration-workflow.md`，编码执行标准见 `references/coding-conventions.md`。

### 阶段五：回归防护（regression_guard）

```bash
python scripts/regression_guard.py record --output <基线.json>
python scripts/regression_guard.py compare --baseline <基线.json> --current <当前.json> --json
```

某测试变更前通过、变更后失败 = 回归 = Critical；`compare` 有回归即退出码 1。

两点必须先知道再用它当门禁：
- 判据是"同名测试 pass→fail"**加上"通过过的测试不得无故消失"**：删除、改名、skip、清空套件都会让 `unexplained_removed_pass` 非空并判红（退出码 1）。有意的删除用 `--allow-removed <名字>`（可重复）或 `--allow-removed-file <路径>`（每行一个名字、`#` 注释）逐条放行，且会被单独记进 `findings` 与 `removed_pass`/`removed_fail`。删掉的是**失败**的测试不算——那属于合法清理，记在 `removed_fail`。
- `non_asymmetric_score` 不是文档承诺的 [0,1] 非对称分：无新增测试时分母为 1，实测"3 个改进 + 1 个真回归"得 +1.98。硬门有效，这个分数不要引用它下结论。
- `record` 没有 `--json`（它写文件）；pytest / cargo 解析器不产出 duration，性能回归档对这两类 runner 不生效。

## 按需加载索引

脚本给出数据，判定规则按需读对应参考文档：

| 场景 | 读这份 |
|------|--------|
| 判定 DIP/ADP/SOLID 违规与假阳性防护 | `architecture-principles.md` |
| 脚本逐条判据、覆盖盲区（先读它再引用任何数字） | `architecture-principles.md` §四「脚本实测口径」 |
| 设计架构师需求文档、程序员实现循环 | `collaboration-workflow.md` |
| 具体语言编码标准（C/C++/Go/Rust/TS） | `coding-conventions.md` |
| MI 公式细节与技术债 Pain×Spread 排序 | `quality-metrics.md` |
| 基线记录与非对称评分细则 | `regression-guard.md` |
| 新项目工程结构（src/bin 强制规范） | `engineering-responsibility.md` |

## 质量门禁

交付前必须同时满足：

| 门禁 | 阈值 | 来源 | 脚本能否直接判红 |
|------|------|------|------------------|
| 健康分 | ≥ 70 | 阶段三 | 能，但无规模归一，只可同范围前后比；跨规模看 `health_score.penalty_per_kloc` |
| 零退化率 | = 100% | 阶段五 | 能（`compare` 退出码 1）；通过过的测试消失/改名/清空同样判红，有意的删除须 `--allow-removed` 放行 |
| 新增代码 MI | ≥ 15 | 阶段三 | 需自己按改动文件逐个跑 `--file`，脚本无"新增代码"概念 |
| 无新增循环依赖 | 0 项 | 阶段二 R5 | 部分：相对导入与包内环检不出，"0 项"≠无环 |

## 脚本工具集

| 脚本 | 阶段 | 实际参数（`--help` 为准） | 输出 |
|------|------|---------------------------|------|
| `arch_scan.py` | 一 | `--target`（必填）`--json --depth N`（默认 5） | 目录树、入口点、技术栈、目录级模块 fan-in/out |
| `dep_graph.py` | 一 | `--target`（必填）`--json --output F --format mermaid\|dot --max-depth N` | 一级目录级依赖图、环、Mermaid/DOT |
| `risk_diagnose.py` | 二 | `--target` 或 `--file`，`--json --risk R1..R6`（可重复）`--min-severity` | R1-R6 四段式发现 + 健康分 |
| `quality_metrics.py` | 三 | `--target` 或 `--file`，`--json --min-cc N --quiet` | MI/CC/HV/健康分/热点 |
| `regression_guard.py` | 五 | 子命令 `record --output F [--test-cmd S] [--cwd D]` / `compare --baseline F --current F [--json] [--allow-removed N] [--allow-removed-file P]` / `evoscore --history F [--gamma G] [--json]` | 测试基线、回归对比（含测试消失判定）、迭代分 |

阶段四（增量优化）是方法论，无脚本；双智能体流程见 `references/collaboration-workflow.md`。

已知接口差异：`--min-cc` 只过滤 JSON 里的函数清单，不过滤 `hotspots` 与 `average_cc/max_cc`，所以带不带该参数报告的聚合值口径不同；`evoscore` 需要外部历史数组（字段 `iteration/passed/target/regressions`），本仓无生成器，`record` 也不产出它，属于手工维护的可选功能。

四个扫描脚本的语言表与忽略目录表**并不相同**（`.java/.kt` 只有 `arch_scan` 和 `quality_metrics` 认；`venv`/`testdata`/`env` 各脚本过滤与否不一致），同一个 `--target` 下各阶段看到的可能不是同一批文件，`files_analyzed` 必须逐阶段核对再比结论。

全部 Python 3.10+ 标准库零依赖（CI 实测 3.10 / 3.13），输出结构化 JSON，Windows 下自动强制 UTF-8 输出。

## 已知限制（引用脚本结论前必读）

以下每一条都是实测确认的行为，不是理论上的可能：

1. **空结果 ≠ 没问题**。R2/R3/R5/R6 的盲区都以"静默返回 0 条"的形式出现，不报错也不降级。
2. **R5 看不见包内循环**：`from . import x` 不建依赖边；同一组文件改成绝对导入才报得出环。判"无循环"前先看项目的导入风格。
3. **R5 的基础设施判定是词边界匹配，不是子串**：`costs`/`post`/`host`/`netlog` 不会再被判成"领域层依赖基础设施"（改前 6 个非基础设施名里 4 个误报 Critical，实测已归零）。代价是**长名字须显式登记**：`sqlalchemy` 这类现在靠标记表里显式那条才认得，如果你的项目用了别的 DB 驱动（如 `mysql`/`aiomysql`），它不会自动命中——需要时直接往 `INFRA_MARKERS` 加一行。
4. **R3 的跨上下文条目是"可能"不是"定论"**：同一份代码放同目录出 Critical、放不同目录出 Warning（都报了，严重度分层）。跨上下文那档脚本分不出"复制粘贴的同一决策"与"各模块独立演化的相似 util"——remedy 里会让你二选一，别直接照搬。另一个未修的刷屏源：每个不同的数字面量各出一条 Critical。
5. **R4 按单文件数实现**：抽象类与其唯一实现分处两文件（常见布局）检不出；同文件 `interface + class` 的惯用写法必报。
6. **R6 的贫血判据只覆盖 Python，且分两档**："公开面全是访问器"给 Warning（这是明确信号），"只有字段无任何方法"只给 Suggestion——脚本分不出"贫血领域对象"和"值对象/ORM 实体"，后者同样长这样，需要你自己读代码定性。改之前这条判据是逻辑不可达的（详见 `references/architecture-principles.md` §四 口径表）。
7. **非 Python 的 CC 是正则近似**：`&&`/`||`/`?`/`=>` 已计入（改前因标点分支被塞进 `\b` 组而全部漏计，实测 5 个用例全低估，已修），但注释与字符串仍会被算进花括号配对的函数边界，`switch`/`match` 本体与 case 臂都计一次；Rust/TS 的发现位置串可能带 `pub`/`export` 而非函数名。数字当提示用。
8. **dep_graph 的模块 = `--target` 下一级目录**：指向仓库根时 `src/` 布局会塌成一个节点、边为空。
9. **回归防护的硬门已覆盖"测试消失"**：删除 / skip / 改名 / 清空套件都会判红，有意的删除用 `--allow-removed` 或 `--allow-removed-file` 逐条放行并留痕；删掉的是失败测试则不算。仍要注意的是 `--allow-removed` 可以被人为滥用（把真回归的测试"有意删除"掉并放行），所以它必须和"测试总数不得缩减"这类外部自检一起用（`references/regression-guard.md` §5.1 给了可直接用的步骤）。
10. **`non_asymmetric_score` 不可用于结论**：实测"3 改进 + 1 真回归"得 +1.98，方向与文档承诺相反；有效的只有回归列表与退出码。
11. **架构级判断不由脚本给出**：分层是否合理、边界是否泄漏、抽象是否多余、命名是否属于统一语言，只能靠读代码得出。脚本的作用是把怀疑范围缩小到具体文件，不是替你判定。

## 协同

以下能力已拆分为独立技能，不再属于本仓库职责：

- `anti-ai-flavor`：AI 味检测专项（detect_code_ai / detect_text_ai）
- `vuln-hunting`：安全扫描与漏洞挖掘（vuln-scan.ps1 / wf.ps1）
- `project-launcher`：新项目元编排
