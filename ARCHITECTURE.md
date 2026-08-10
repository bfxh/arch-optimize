# 架构优化文档（arch-optimize）

本仓库的**架构优化能力**以技能（skill）形式提供，覆盖从**架构分析**到**增量优化**到**回归防护**的完整工作流。本文档是架构部分的总览；完整技能正文见 `SKILL.md`。

## 核心工作流（五阶段）

| 阶段 | 名称 | 角色 | 目标 |
|------|------|------|------|
| 一 | 架构感知 (Perceive) | Architect | 建立代码库全景认知：目录结构、入口点、模块边界、依赖关系、技术栈、架构文档索引 |
| 二 | 风险诊断 (Diagnose) | Architect | 扫描六大衰退风险（R1-R6），定位热点区域 |
| 三 | 质量度量 (Measure) | Architect | 用量化指标建立质量基线（MI / CC / 健康分） |
| 四 | 增量优化 (Optimize) | Programmer | 在架构师约束下执行增量式改进（每次最多 5 项） |
| 五 | 回归防护 (Guard) | Programmer | 确保优化不破坏现有功能（零退化率） |

**铁律：在完成风险诊断前，绝不提出修复建议。**

## 六大衰退风险（R1-R6）

| 风险 | 诊断问题 | 严重性阈值 |
|------|---------|-----------|
| R1 认知过载 | 理解这段代码需要多少脑力？ | 函数>50行=Critical；嵌套>5层=Critical |
| R2 变更传播 | 改一处会波及多少不相关的东西？ | 触及>5文件=Critical；3-5=Warning |
| R3 知识重复 | 同一决策是否在多处表达？ | 跨3+模块重复=Critical |
| R4 偶发复杂性 | 代码是否比它解决的问题更复杂？ | 主观评估+圈复杂度>15=Critical |
| R5 依赖失序 | 依赖是否朝一致方向流动？ | 循环依赖=Critical；领域→基础设施=Critical |
| R6 领域模型扭曲 | 代码是否忠实表达了要解决的问题？ | 贫血模型=Critical；命名不匹配=Warning |

每条发现遵循四段式：**Symptom → Source → Consequence → Remedy**。

**假阳性防护**：
- 组合根装配具体依赖 ≠ DIP 违规
- DTO / 持久化记录 / API 载荷纯数据 ≠ 贫血模型
- 不同限界上下文间相似代码 ≠ DRY 违规
- 线性+清晰命名+卫语句的长函数 ≠ 认知过载

## 质量度量（静态指标）

- **维护性指数 (MI)** = MAX(0, (171 - 5.2×ln(HV) - 0.23×CC - 16.2×ln(LOC)) × 100/171)
  - MI > 20 = 高可维护性；10 ≤ MI ≤ 20 = 中等；MI < 10 = 低
- **圈复杂度 (CC)**：>15 = Critical；11-15 = Warning；≤10 = OK
- **健康分** = 100 - 15×Critical - 5×Warning - 1×Suggestion（最低 0）

**技术债优先级**（Pain × Spread 矩阵）：
| Priority | 分类 | 行动 |
|----------|------|------|
| 7-9 | Critical debt | 下个迭代解决 |
| 4-6 | Scheduled debt | 季度内规划 |
| 1-3 | Monitored debt | 记录监控 |

## 回归防护

- **回归定义**：某个测试在变更前通过、变更后失败 = 回归
- 变更前运行完整测试套件记录基线 → 变更后比对 → 任何回归 = Critical
- **质量门禁**：健康分 ≥ 70 方可合并；零退化率 = 100% 方可合并；新增代码 MI ≥ 15；无新增循环依赖

## 可执行脚本

| 脚本 | 对应阶段 | 功能 |
|------|---------|------|
| `scripts/arch_scan.py` | 一 | 目录扫描、入口点检测、技术栈识别、文档定位 |
| `scripts/dep_graph.py` | 一 | 依赖图生成（Mermaid/DOT）、循环依赖检测 |
| `scripts/risk_diagnose.py` | 二 | R1-R6 风险扫描、四段式发现 |
| `scripts/quality_metrics.py` | 三 | MI/CC/HV/健康分计算、热点识别 |
| `scripts/regression_guard.py` | 五 | 测试基线记录、回归对比 |

Python 3.8+ 标准库零依赖、JSON 输出、幂等设计、多语言支持（Python/Go/C/C++/Rust/TypeScript/JavaScript）。

**智能体调用模式**：
1. 单阶段调用：`python3 scripts/risk_diagnose.py --target ./src --json`
2. 全流程调用：arch_scan → dep_graph → risk_diagnose → quality_metrics → regression_guard
3. 管道模式：前一脚本的 JSON 输出作为后一脚本的输入上下文

## MCP 插件工具（Level 3）

基于 FastMCP（stdio 传输），5 个结构化工具：

| MCP 工具 | 阶段 | 只读 | 幂等 |
|---------|------|------|------|
| `arch_optimize_scan` | 一 | ✓ | ✓ |
| `arch_optimize_dep_graph` | 一 | ✓ | ✓ |
| `arch_optimize_risk_diagnose` | 二 | ✓ | ✓ |
| `arch_optimize_quality_metrics` | 三 | ✓ | ✓ |
| `arch_optimize_regression_guard` | 五 | ✗ | ✗ |

设计原则：子进程封装（零导入耦合）、统一错误处理（`{"error": ..., "returncode": N}`）、超时保护（300s，record 900s）、输入验证、工具注解（readOnly/destructive/idempotent/openWorld）。

## 输出格式

每次执行产出结构化报告：架构全景（Mermaid 图 + 技术栈）→ 风险诊断（R1-R6 四段式）→ 质量度量表 → 优化计划（本期最多 5 项）→ 回归检查。

## 设计理念

1. **诊断先于修复**：完成风险诊断前绝不提出修复建议
2. **增量优于大规模**：每次最多 5 个改进需求，小步快跑
3. **回归零容忍**：破坏现有功能的代价 > 增加新功能的收益
4. **分工优于全能**：架构师管战略，程序员管执行，避免上帝视角
5. **量化优于直觉**：MI、健康分提供客观基线
6. **假阳性防护**：避免将设计模式正常用法误判为违规
7. **可执行优于纯文档**：所有理论公式和检测规则均有对应脚本实现
8. **协议化优于命令行**：MCP 插件封装使工具可被任意 AI 智能体通过标准协议发现和调用

## AAA 级视觉质量保障

- 分派子代理，每个子代理单独负责一部分，让项目达到极致完美
- 视觉审查子代理是**非常严厉的批评家**，不达 AAA 级就继续迭代
- **不停止**，直到每个子代理都对质量感到惊叹

质量惊叹标准：代码经得起逐行审视（无死代码/占位符/假实现）、架构层次清晰、文档无套话、视觉排版美观。
