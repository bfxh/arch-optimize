---
name: "arch-optimize"
description: "架构优化技能：融合SWE-CI演进质量评估、六大衰退风险扫描和架构师-程序员双智能体协作，提供编码规范、质量度量与回归防护。内置5个可执行脚本（arch_scan/risk_diagnose/quality_metrics/dep_graph/regression_guard），支持AI智能体直接调用获取结构化JSON数据。在需要架构审查、技术债评估、代码重构、质量提升时调用。"
version: "2.0"
---

# 架构优化技能 (Architecture Optimization)

## 定位

本技能融合三大理论体系，提供从**架构分析**到**增量优化**到**回归防护**的完整工作流：

1. **SWE-CI 演进质量评估**（中山大学+阿里）：以 EvoScore 衡量代码长期维护能力，非对称评分惩罚回归
2. **六大衰退风险扫描**（brooks-lint，基于12本经典工程书籍）：R1-R6 结构化诊断
3. **架构师-程序员双智能体协作**：战略层与执行层分离，避免上帝视角

## 调用时机

- 用户请求架构审查 / 架构优化 / 代码重构
- 用户请求技术债评估 / 代码质量提升
- 用户请求编码规范检查 / 规范制定
- 大规模重构前的影响分析
- 持续集成中的代码质量门禁
- 新成员入职时的代码库导览
- 用户提到"架构""优化""技术债""代码质量""重构""可维护性"等关键词

## 核心工作流（五阶段）

### 阶段一：架构感知（Architect: Perceive）

目标：建立代码库的全景认知。

```
输入：项目根目录
动作：
  1. 扫描目录结构，识别入口点、模块边界、依赖关系
  2. 绘制 Mermaid 模块依赖图（节点=顶层模块，边=导入关系，虚线=循环依赖）
  3. 识别技术栈、构建系统、测试框架
  4. 定位架构文档（SPEC.md / CLAUDE.md / REASONIX.md / CONTRIBUTING.md 等）
输出：架构全景图 + 技术栈摘要 + 文档索引
```

**可执行脚本**：
```bash
# 架构感知扫描（目录结构、入口点、技术栈、文档定位）
python3 scripts/arch_scan.py --target <项目根目录> --json

# 依赖图生成（Mermaid 图 + 循环依赖检测）
python3 scripts/dep_graph.py --target <项目根目录> --json
```
AI智能体可直接调用上述脚本获取结构化JSON，无需人工解析目录结构。

### 阶段二：风险诊断（Architect: Diagnose）

目标：扫描六大衰退风险，定位热点区域。

**铁律：在完成风险诊断前，绝不提出修复建议。**

扫描六大衰退风险（详见 `references/architecture-principles.md`）：

| 风险 | 诊断问题 | 严重性阈值 |
|------|---------|-----------|
| R1 认知过载 | 理解这段代码需要多少脑力？ | 函数>50行=Critical；嵌套>5层=Critical |
| R2 变更传播 | 改一处会波及多少不相关的东西？ | 触及>5文件=Critical；3-5=Warning |
| R3 知识重复 | 同一决策是否在多处表达？ | 跨3+模块重复=Critical |
| R4 偶发复杂性 | 代码是否比它解决的问题更复杂？ | 主观评估+圈复杂度>15=Critical |
| R5 依赖失序 | 依赖是否朝一致方向流动？ | 循环依赖=Critical；领域→基础设施=Critical |
| R6 领域模型扭曲 | 代码是否忠实表达了要解决的问题？ | 贫血模型=Critical；命名不匹配=Warning |

每条发现必须遵循四段式结构：**Symptom → Source → Consequence → Remedy**

**假阳性防护**（详见 `references/architecture-principles.md` 假阳性章节）：
- 组合根装配具体依赖 ≠ DIP 违规
- DTO / 持久化记录 / API 载荷纯数据 ≠ 贫血模型
- 不同限界上下文间相似代码 ≠ DRY 违规
- 线性+清晰命名+卫语句的长函数 ≠ 认知过载

**可执行脚本**：
```bash
# R1-R6 全面风险诊断（输出四段式结构化发现）
python3 scripts/risk_diagnose.py --target <项目根目录> --json

# 按风险类型过滤
python3 scripts/risk_diagnose.py --target <项目根目录> --risk R5 --json

# 只显示 Critical 级别
python3 scripts/risk_diagnose.py --target <项目根目录> --min-severity Critical --json
```
脚本输出每条发现均遵循 Symptom → Source → Consequence → Remedy 四段式结构，AI智能体可直接解析用于报告生成。

### 阶段三：质量度量（Measure）

目标：用量化指标建立质量基线。

**静态指标**（详见 `references/quality-metrics.md`）：
- **维护性指数 (MI)** = MAX(0, (171 - 5.2×ln(HV) - 0.23×CC - 16.2×ln(LOC)) × 100/171)
  - MI > 20 = 高可维护性（绿色）；10 ≤ MI ≤ 20 = 中等（黄色）；MI < 10 = 低（红色）
- **圈复杂度 (CC)**：>15 = Critical；11-15 = Warning；≤10 = OK
- **健康分** = 100 - 15×Critical - 5×Warning - 1×Suggestion（最低0）

**动态指标**（EvoScore 启发，详见 `references/quality-metrics.md`）：
- **演进评分** = Σ(γ^i × a(c_i)) / Σ(γ^i)，γ ≥ 1，后期迭代权重更大
- **零退化率** = 完全无回归的任务比例（目标：100%）
- **非对称评分**：破坏现有功能惩罚 > 增加新功能奖励

**技术债优先级**（Pain × Spread 矩阵）：
| Priority | 分类 | 行动 |
|----------|------|------|
| 7-9 | Critical debt | 下个迭代解决 |
| 4-6 | Scheduled debt | 季度内规划 |
| 1-3 | Monitored debt | 记录监控 |

**可执行脚本**：
```bash
# 质量度量计算（MI、CC、HV、健康分）
python3 scripts/quality_metrics.py --target <项目根目录> --json

# 分析单个文件
python3 scripts/quality_metrics.py --file <文件路径> --json

# 只显示 CC >= 10 的函数
python3 scripts/quality_metrics.py --target <项目根目录> --min-cc 10
```
脚本计算维护性指数(MI)、圈复杂度(CC)、Halstead容量(HV)和健康分，AI智能体可直接引用量化数据。

### 阶段四：增量优化（Programmer: Optimize）

目标：在架构师约束下执行增量式改进。

**核心约束：每次迭代最多处理5个最紧迫的改进需求。**

```
架构师产出：
  - 高层次自然语言需求（不包含具体实现细节）
  - 每个需求的优先级排序（基于 Pain × Spread）
  - 预期效果和风险评估

程序员执行：
  1. 将自然语言需求转化为技术规格
  2. 制定实现计划（最小化变更范围）
  3. 执行代码修改
  4. 运行测试套件验证
```

**编码规范**（详见 `references/coding-conventions.md`）：
- 通用规范：函数≤50行、嵌套≤3层、参数≤4个、魔法数字必须命名
- C/C++：RAII、智能指针、const 正确性、异常安全保证
- Rust：所有权语义、unsafe 隔离、trait 边界、零成本抽象
- Go：错误包装 `fmt.Errorf("...: %w", err)`、单一职责包、CGO_ENABLED=0 静态构建
- TypeScript：严格模式、判别联合、不可变优先、branded types

### 阶段五：回归防护（Guard）

目标：确保优化不破坏现有功能。

**回归定义**：某个测试在变更前通过、变更后失败 = 回归。

**防护措施**（详见 `references/regression-guard.md`）：
1. 变更前运行完整测试套件，记录基线通过率
2. 变更后运行相同测试套件，比对差异
3. 任何回归 = Critical，必须修复后才能合并
4. 追踪零退化率趋势
5. 采用非对称评分：回归扣分 > 改进加分

**质量门禁**：
- 健康分 ≥ 70 方可合并
- 零退化率 = 100% 方可合并（硬性门禁）
- 新增代码 MI ≥ 15
- 无新增循环依赖

**可执行脚本**：
```bash
# 步骤1: 变更前记录基线
python3 scripts/regression_guard.py record --output baseline.json

# 步骤2: 变更后记录当前状态
python3 scripts/regression_guard.py record --output current.json

# 步骤3: 对比基线与当前（计算零退化率、非对称评分）
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json

# 步骤4: 多轮迭代的 EvoScore 计算
python3 scripts/regression_guard.py evoscore --history history.json --gamma 1.5
```
脚本自动检测测试框架（go test / pytest / jest / cargo test），计算零退化率和非对称评分，AI智能体可直接读取 `gate_passed` 字段判断是否通过质量门禁。

## 详细参考文档

| 文档 | 内容 |
|------|------|
| `references/architecture-principles.md` | Clean Architecture、SOLID、DDD、六大衰退风险、假阳性防护 |
| `references/coding-conventions.md` | C/C++/Rust/Go/TypeScript 编码规范、错误处理、命名约定 |
| `references/quality-metrics.md` | MI 公式、EvoScore 演进评分、健康分、Pain×Spread 矩阵、SQALE 技术债 |
| `references/regression-guard.md` | 零退化率、回归检测模式、非对称评分、CI 门禁配置 |
| `references/collaboration-workflow.md` | 架构师-程序员分工、信息隔离、增量优化策略、反馈循环 |

## 脚本工具集 (Script Toolkit)

本技能内置5个可执行脚本，将文档中的理论公式和检测规则转化为可运行的代码。AI智能体可通过CLI调用并获取结构化JSON输出。

**设计原则**：Python 3.8+ 标准库零依赖、JSON输出、幂等设计、多语言支持。

### 脚本总览

| 脚本 | 对应阶段 | 功能 | 输出格式 |
|------|---------|------|---------|
| `scripts/arch_scan.py` | 阶段一 | 目录扫描、入口点检测、技术栈识别、文档定位 | JSON / 人类可读 |
| `scripts/dep_graph.py` | 阶段一 | 依赖图生成（Mermaid/DOT）、循环依赖检测 | JSON / Mermaid / DOT |
| `scripts/risk_diagnose.py` | 阶段二 | R1-R6 六大衰退风险扫描、四段式发现 | JSON / 人类可读 |
| `scripts/quality_metrics.py` | 阶段三 | MI/CC/HV/健康分计算、热点识别 | JSON / 人类可读 |
| `scripts/regression_guard.py` | 阶段五 | 测试基线记录、回归对比、EvoScore计算 | JSON / 人类可读 |

### 智能体调用模式

AI智能体可按以下模式调用脚本：

```
1. 单阶段调用：仅执行某个阶段的脚本
   python3 scripts/risk_diagnose.py --target ./src --json

2. 全流程调用：按阶段顺序执行所有脚本
   arch_scan → dep_graph → risk_diagnose → quality_metrics → regression_guard

3. 管道模式：前一脚本的JSON输出作为后一脚本的输入上下文
   arch_scan --json | → 提取模块列表 → risk_diagnose --target <模块>
```

### 支持的语言

| 语言 | 扩展名 | 导入解析 | CC计算 | 函数提取 |
|------|--------|---------|--------|---------|
| Python | .py | ast 模块 | ast 遍历 | ast.FunctionDef |
| Go | .go | import 解析 | 正则+花括号匹配 | func 关键字 |
| C/C++ | .c/.h/.cpp/.hpp | #include 解析 | 正则+花括号匹配 | 函数签名匹配 |
| Rust | .rs | use/mod 解析 | 正则+花括号匹配 | fn 关键字 |
| TypeScript | .ts/.tsx | import/from 解析 | 正则+花括号匹配 | function/箭头函数 |
| JavaScript | .js/.jsx | import/require 解析 | 正则+花括号匹配 | function/箭头函数 |

## MCP 插件工具集 (MCP Plugin Tools, v3.0)

本技能已升级为 Level 3 MCP 插件，AI智能体可通过 MCP 协议直接调用5个结构化工具，无需通过CLI命令行。

**MCP 服务器**：`arch_optimize`（基于 FastMCP 框架，stdio 传输）
**服务器文件**：`scripts/mcp_server.py`
**工具描述符**：`tools/arch_optimize_*.json`

### MCP 工具总览

| MCP 工具 | 对应阶段 | CLI 脚本 | 只读 | 幂等 |
|---------|---------|---------|------|------|
| `arch_optimize_scan` | 阶段一 | arch_scan.py | ✓ | ✓ |
| `arch_optimize_dep_graph` | 阶段一 | dep_graph.py | ✓ | ✓ |
| `arch_optimize_risk_diagnose` | 阶段二 | risk_diagnose.py | ✓ | ✓ |
| `arch_optimize_quality_metrics` | 阶段三 | quality_metrics.py | ✓ | ✓ |
| `arch_optimize_regression_guard` | 阶段五 | regression_guard.py | ✗ | ✗ |

### 工具参数详解

**arch_optimize_scan**：架构感知扫描
- `target` (str, 必填): 项目根目录路径
- `depth` (int, 默认5): 最大目录扫描深度 (1-20)

**arch_optimize_dep_graph**：依赖图生成
- `target` (str, 必填): 源代码目录路径
- `format` (str, 默认"mermaid"): 图格式，"mermaid" 或 "dot"
- `max_depth` (int, 默认0): 最大扫描深度，0=无限

**arch_optimize_risk_diagnose**：风险诊断
- `target` (str, 必填): 项目目录路径
- `risk` (str, 可选): 过滤单一风险类型 "R1"-"R6"
- `min_severity` (str, 可选): 最低严重级别 "Critical"/"Warning"/"Suggestion"

**arch_optimize_quality_metrics**：质量度量
- `target` (str, 可选): 分析目录（与 file 互斥）
- `file` (str, 可选): 分析单个文件（与 target 互斥）
- `min_cc` (int, 默认0): 只报告 CC >= 此值的函数

**arch_optimize_regression_guard**：回归防护
- `action` (str, 必填): 子命令 "record"/"compare"/"evoscore"
- `target` (str, record可选): 工作目录
- `baseline` (str, compare必填): 基线JSON文件
- `current` (str, compare必填): 当前JSON文件
- `history` (str, evoscore必填): 历史JSON文件
- `gamma` (float, 默认1.5): 折扣因子
- `test_cmd` (str, record可选): 测试命令
- `output` (str, record必填): 输出JSON文件路径

### 三级演进路径

| 级别 | 形态 | 调用方式 | 版本 |
|------|------|---------|------|
| Level 1 | 纯文档 | AI阅读文档后手动分析 | v1.0 |
| Level 2 | 脚本增强 | CLI命令调用，JSON输出 | v2.0 |
| Level 3 | MCP插件 | MCP协议直接调用，结构化工具 | v3.0 |

### 设计原则（MCP层）

- **子进程封装**：每个MCP工具通过subprocess调用对应CLI脚本，零导入耦合
- **统一错误处理**：非零退出码返回 `{"error": "...", "returncode": N}` JSON
- **超时保护**：默认300秒，record操作900秒
- **输入验证**：Pydantic Field 约束参数范围和类型
- **工具注解**：readOnlyHint / destructiveHint / idempotentHint / openWorldHint

## 输出格式

每次执行后产出结构化报告：

```markdown
# 架构优化报告

## 1. 架构全景
[Mermaid 依赖图 + 技术栈摘要]

## 2. 风险诊断
### R1 认知过载
- [Critical] `path/to/file:funcName`
  - Symptom: 函数长达 87 行，嵌套 6 层
  - Source: 缺少中间抽象，条件逻辑内联
  - Consequence: 新开发者需 30+ 分钟理解，修改易引入缺陷
  - Remedy: 提取卫语句前置 + 策略模式消除分支

### R2-R6 ...

## 3. 质量度量
| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| 健康分 | 72 | >=80 | Warning |
| 平均 MI | 14.3 | >=18 | Warning |
| 零退化率 | 100% | 100% | OK |
| 技术债 | 4项Critical | 0项 | Critical |

## 4. 优化计划（本期最多5项）
1. [Priority 9] 重构 xxx 模块，消除循环依赖
2. [Priority 6] 提取 yyy 服务，分离关注点
...

## 5. 回归检查
- 基线测试通过率: 142/145
- 变更后测试通过率: 145/145
- 零退化率: 100% OK
```

## 与现有技能的协同

| 场景 | 推荐技能组合 |
|------|-------------|
| 全面架构审查 | arch-optimize + brooks-audit |
| PR 代码审查 | arch-optimize(阶段二) + brooks-review |
| 技术债路线图 | arch-optimize(阶段三) + brooks-debt |
| 发布前健康检查 | arch-optimize(全流程) + brooks-health |
| 决策记录 | arch-optimize + archcore:decide |
| 编码前上下文 | archcore:context -> arch-optimize(阶段四) |

## 设计理念

本技能的设计基于以下原则：

1. **演进优于快照**：代码质量不是单次状态，而是随时间变化的轨迹（SWE-CI 核心洞察）
2. **诊断先于修复**：在完成风险诊断前绝不提出修复建议（brooks-lint 铁律）
3. **增量优于大规模**：每次最多5个改进需求，小步快跑（SWE-CI 架构师模式）
4. **回归零容忍**：破坏现有功能的代价 > 增加新功能的收益（EvoScore 非对称设计）
5. **分工优于全能**：架构师管战略，程序员管执行，避免上帝视角（SWE-CI 双智能体）
6. **量化优于直觉**：MI、健康分、EvoScore 提供客观基线
7. **假阳性防护**：避免将设计模式正常用法误判为违规
8. **可执行优于纯文档**：所有理论公式和检测规则均有对应脚本实现，AI智能体可直接调用获取量化数据（v2.0升级）
9. **协议化优于命令行**：MCP插件封装使工具可被任意AI智能体通过标准协议发现和调用，无需解析CLI用法（v3.0升级）
