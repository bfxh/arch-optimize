---
name: "arch-optimize"
description: "架构优化技能 v3.0：对工程负责的根哲学——融合 SWE-CI 演进质量评估、六大衰退风险扫描、架构师-程序员双智能体协作、反AI味检测、项目结构约定（src+bin分离）、游戏开发技能合并（含 Godot MCP 集成 + 本地漏洞挖掘脚本 vuln-scan.ps1、C/C++ 安全检测(10种)、配置安全审计）、Ponytail 懒人模式、文档技术方向/实现愿景模板、Workflow CLI v2.2、官方脚本工具集（arch_scan/dep_graph/risk_diagnose/quality_metrics/regression_guard 5 个可执行脚本 + mcp_server.py MCP 插件，纯 Python 标准库零依赖输出结构化 JSON）。从架构健康到内容真实性到工程责任感的完整质量闭环。所有软件/游戏项目必须在同一文件夹内分 src/ 和 bin/。工程之上才是其他。在架构审查、技术债评估、代码重构、质量提升、AI味检测、工程结构评审、游戏开发时调用。"
version: "3.0"
runAs: inline
allowed-tools: read_file, write_file, edit_file, grep, glob, bash
---

# 架构优化技能 v3.0 (Architecture Optimization + Anti-AI-Flavor + Godot MCP + 本地漏洞挖掘 + 官方脚本工具集)

## 定位

**根哲学：对工程负责。** 这是本技能以及所有关联 skill 的根本原则。不管什么项目类型（软件、游戏、舆论分析、漏洞挖掘），第一原则是对工程负责——交付的每一行代码、每一份文档、每一个决策，都必须经得起工程检验。

本技能是**架构健康 + 内容真实性 + 工程责任**的三重质量门禁，融合四大理论体系：

1. **SWE-CI 演进质量评估**（中山大学+阿里）：以 EvoScore 衡量代码长期维护能力，非对称评分惩罚回归
2. **六大衰退风险扫描**（brooks-lint，基于 12 本经典工程书籍）：R1-R6 结构化诊断
3. **架构师-程序员双智能体协作**：战略层与执行层分离，避免上帝视角
4. **反AI味检测**（本 v2.1 新增）：18 个 AI 特有低质量模式扫描，确保交付物经得起人类逐行审视

**v3.0 核心升级（含 v2.5 历史）**：
- **本地漏洞挖掘脚本**：新增 `scripts/vuln-scan.ps1`，全本地执行，覆盖 GDScript 安全(15种模式)、Rust 不安全模式(15种)、MCP 配置审计(10种)、密钥泄露(20种)、依赖审计、C/C++ 安全检测(10种)、配置安全审计
- **Workflow CLI v2.2**：新增 `local-scan` 命令，`vuln-hunt` 改为本地脚本优先 + MCP 辅助，新增 `audit` 和 `hardening` 命令
- **本地优先原则**：挖漏洞以本地脚本为主，MCP 工具为辅，不依赖任何外部 API
- **Godot MCP 集成**：Meow Godot MCP（MIT 授权，零依赖 C++ GDExtension），50 个 MCP 工具直接控制 Godot 编辑器
- **漏洞挖掘自动化**：Godot MCP 在挖漏洞时自动启动游戏→检查运行时错误→捕获截图→关闭编辑器
- **非架构 bug 不停止流程**：大规模开发持续前进
- **综合安全审计(audit)**：一键执行全部安全检测（GDScript + Rust + C/C++ + MCP 配置 + 密钥 + 配置审计）
- **安全加固(hardening)**：根据审计结果自动生成修复建议并应用
- 根哲学"对工程负责"贯穿所有阶段，新增"工程>项目>其他"层级原则
- 所有软件/游戏项目强制同一文件夹内 src/ + bin/ 分离（游戏额外区分 bin/debug/ 和 bin/release/）
- 游戏开发技能合并为本技能子模块（game-dev），插件默认合并
- 文档模板强制要求"技术方向"和"实现愿景"（要搞什么、至少呈现什么、呈现在哪）
- 整合 Ponytail 懒人模式（YAGNI + 7 级阶梯，作为编码前置检查）
- 引用 MCP Codebase-Memory（知识图谱）+ aether-trae-bridge（IDE 自动补全）+ Godot MCP（游戏控制）

## 调用时机

- 用户请求架构审查 / 架构优化 / 代码重构
- 用户请求技术债评估 / 代码质量提升
- 用户请求编码规范检查 / 规范制定
- 大规模重构前的影响分析
- 持续集成中的代码质量门禁
- **AI 生成代码后**（交付前必须检测 AI 味）
- **AI 撰写文档/报告后**（展示前必须检测 AI 味）
- 用户提到"架构""优化""技术债""代码质量""重构""AI味""假""占位符""指鹿为马"等关键词

## 核心工作流（七阶段）

### 阶段零：工程前置检查（v2.2 强化 - Engineering Responsibility）

目标：在进入架构分析之前，先确认工程基础是否正确。

**铁律：工程结构不对，一切优化都是空中楼阁。**
**铁律二：工程之上才是其他。** 先搭好工程结构，再谈业务逻辑、功能特性、优化方向。工程是地基，地基不稳，上层建筑毫无意义。**工程>项目>其他**——工程层级决定项目成败，项目层级决定其他一切。所有软件/游戏项目必须在**同一个文件夹**内分 src/ 和 bin/。

```
检查项：
  1. 项目结构是否遵循 src/ + bin/ 分离？
     - src/ 只放源代码
     - bin/ 放编译产物（可执行文件、DLL、包）
     - 游戏项目额外区分 bin/debug/ 和 bin/release/
  2. 是否有 README / 架构文档？
  3. 是否有构建脚本 / CI 配置？
  4. 依赖清单是否明确？（Cargo.toml / package.json / requirements.txt）
  5. 是否有测试套件？

违规处理：
  - 缺少 src/ 或 bin/ 分离 = Warning（建议修复）
  - 无任何文档 = Warning（建议补充）
  - 无构建脚本 = Critical（必须修复，否则无法确保可复现构建）
  - 无依赖清单 = Critical（无法审计依赖风险）
```

**游戏项目额外检查**：
  - assets/raw/ 和 assets/processed/ 是否分离？
  - 引擎代码与游戏逻辑是否分离？
  - 资源管线是否有构建脚本？
  - 是否有性能预算文档？

**与 Ponytail 的协同**：Ponytail（懒人模式）建议在阶段零之前或阶段零中并行调用，先问"这东西真的需要存在吗？"再确定工程结构。

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

**官方脚本（v3.0）**：
```bash
# 架构感知扫描（目录结构、入口点、技术栈、文档定位）
python3 scripts/arch_scan.py --target ./src --json
# 依赖图生成（Mermaid 图 + 循环依赖检测）
python3 scripts/dep_graph.py --target ./src --json
```

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

**官方脚本（v3.0）**：
```bash
# R1-R6 全面风险诊断（输出四段式结构化发现）
python3 scripts/risk_diagnose.py --target ./src --json
# 按风险类型过滤
python3 scripts/risk_diagnose.py --target ./src --risk R5 --json
# 只显示 Critical 级别
python3 scripts/risk_diagnose.py --target ./src --min-severity Critical --json
```

**假阳性防护**（详见 `references/architecture-principles.md` 假阳性章节）：
- 组合根装配具体依赖 ≠ DIP 违规
- DTO / 持久化记录 / API 载荷纯数据 ≠ 贫血模型
- 不同限界上下文间相似代码 ≠ DRY 违规
- 线性+清晰命名+卫语句的长函数 ≠ 认知过载

### 阶段三：质量度量（Measure）

目标：用量化指标建立质量基线。

**静态指标**（详见 `references/quality-metrics.md`）：
- **维护性指数 (MI)** = MAX(0, (171 - 5.2×ln(HV) - 0.23×CC - 16.2×ln(LOC)) × 100/171)
  - MI > 20 = 高可维护性（绿色）；10 ≤ MI ≤ 20 = 中等（黄色）；MI < 10 = 低（红色）
- **圈复杂度 (CC)**：>15 = Critical；11-15 = Warning；≤10 = OK
- **AI味评分 (ai_flavor_score)** = Σ(严重性权重) 封顶 100，越低越好（0=无AI味，100=全是AI味）
  - Blocker=25 分/处，Critical=15 分/处，Warning=5 分/处
- **健康分** = 100 - 15×Critical - 5×Warning - 1×Suggestion - 2×AI_Blocker - 1×AI_Critical（最低0）

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

**官方脚本（v3.0）**：
```bash
# 质量度量计算（MI、CC、HV、健康分）
python3 scripts/quality_metrics.py --target ./src --json
# 分析单个文件
python3 scripts/quality_metrics.py --file src/main.py --json
# 只显示 CC >= 10 的函数
python3 scripts/quality_metrics.py --target ./src --min-cc 10
```

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

**官方脚本（v3.0）**：
```bash
# 步骤1: 变更前记录基线
python3 scripts/regression_guard.py record --output baseline.json --test-cmd "pytest -q"
# 步骤2: 变更后记录当前状态
python3 scripts/regression_guard.py record --output current.json --test-cmd "pytest -q"
# 步骤3: 对比基线与当前（计算零退化率、非对称评分）
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json
# 步骤4: 多轮迭代的 EvoScore 计算
python3 scripts/regression_guard.py evoscore --history history.json --gamma 1.5
```

### 阶段六：AI味净化（v2.0 新增 - Anti-AI-Flavor）

目标：确保交付物经得起人类开发者逐行审视，无 AI 特有的低质量模式。

**铁律：AI味检测结果在交付前必须为"零 Blocker / 零 Critical"方可放行。**

**检测三大维度**（详见 `references/ai-patterns-catalog.md`）：

#### 一、代码反AI味（10 个模式）

| 模式 | 症状 | 严重性 | 修复方式 |
|------|------|--------|---------|
| DEAD-001 死代码 | 未使用的函数、变量、import、类 | Critical | 删除或标记为有意保留 |
| DEAD-002 占位符 | TODO/FIXME/pass/NotImplemented/"模拟实现" | Critical | 实现真实逻辑或告知用户做不到 |
| DEAD-003 假实现 | 内存模拟冒充真实系统、mock 冒充生产代码 | Blocker | 必须用真实实现，禁止用 mock 冒充 |
| DEAD-004 过度注释 | 注释说明显而易见的事 | Warning | 删除无用注释，保留有信息量的注释 |
| DEAD-005 无意义命名 | data1/temp/foo/bar/stuff/thing | Warning | 用描述性名称 |
| DEAD-006 过度工程化 | 不必要的抽象层、过度泛化、YAGNI违反 | Warning | 删除不必要的抽象 |
| DEAD-007 重复模式 | AI 常生成的重复 try-catch/if-else 结构 | Warning | 提取公共逻辑 |
| DEAD-008 虚假错误处理 | catch 了异常但不处理（空catch/只打印） | Critical | 要么处理要么传播，不要吞异常 |
| DEAD-009 幻觉API | 调用不存在的API/库函数/方法签名错误 | Blocker | 验证所有API调用真实存在 |
| DEAD-010 拼凑感 | 代码段之间风格不一致，像是拼接的 | Warning | 统一代码风格 |

#### 二、文本反AI味（8 个模式）

| 模式 | 症状 | 修复方式 |
|------|------|---------|
| TEXT-001 套话开头 | "在当今社会""随着技术的发展""众所周知" | 直接切入主题 |
| TEXT-002 空泛表述 | "具有重要意义""值得关注""不可或缺" | 用具体数据和事实替代 |
| TEXT-003 过度结构化 | 不必要的列表、过多的层次标题 | 按内容自然组织 |
| TEXT-004 虚假自信 | "显然""毫无疑问""必定" | 标注不确定性 |
| TEXT-005 AI常用短语 | "让我们深入探讨""值得注意的是""总而言之" | 用自然人类表达 |
| TEXT-006 信息空洞 | 段落看起来很长但实际信息量为零 | 每段必须有实质信息 |
| TEXT-007 重复赘述 | 同一个观点换三种方式说三遍 | 一个观点说一次 |
| TEXT-008 虚假引用 | 引用不存在的研究/数据/论文 | 只引用真实可验证的来源 |

#### 三、行为反AI味（5 个模式）

| 模式 | 症状 | 修复方式 |
|------|------|---------|
| BEHAV-001 模型骄傲 | "我已完美实现""这是一个出色的方案" | 如实报告，不加自我评价 |
| BEHAV-002 指鹿为马 | 识别错误但声称正确（原型说成背包） | 如实报告，不确定时标注 |
| BEHAV-003 声称存在不展示 | 说"有调研结果"但不展示 | 展示实际内容 |
| BEHAV-004 过度承诺 | 承诺做不到的事 | 只承诺能做到的 |
| BEHAV-005 假装理解 | 没理解用户意图但假装懂了 | 不懂就问 |

#### 可执行脚本检测

本技能内置 2 个 Python 脚本，将检测规则转化为可运行代码：

```bash
# 检测代码 AI 味（扫描整个项目目录）
python3 scripts/detect_code_ai.py --target <项目目录> --json

# 检测单个代码文件
python3 scripts/detect_code_ai.py --file <代码文件路径> --json

# 检测文本 AI 味（扫描文档文件）
python3 scripts/detect_text_ai.py --file <文档路径> --json

# 检测直接传入的文本
python3 scripts/detect_text_ai.py --text "综上所述，AI技术在当今社会具有重要意义" --json
```

**智能体调用模式**：
```
1. 代码交付前：detect_code_ai.py --target <生成代码目录> --json
   → 若存在 Blocker/Critical，必须修复后重新检测，直至 Blocker/Critical 计数为 0

2. 文档交付前：detect_text_ai.py --file <文档> --json
   → 若存在 TEXT-001~008 任意命中，逐条修复

3. 全流程质量门禁：detect_code_ai + detect_text_ai 联合检测
   → 作为本技能阶段六的最终关卡
```

## 官方脚本工具集与 MCP 插件（v3.0 整合 - Official Script Toolkit & MCP Plugin）

> 对齐 GitHub 官方仓库 bfxh/arch-optimize 的 PR 标准。5 个可执行脚本将理论公式和检测规则转化为可运行代码，全部**仅使用 Python 3.8+ 标准库（零外部依赖）**，输出结构化 JSON。MCP 插件（Level 3）通过标准 MCP 协议暴露 5 个结构化工具，任何 AI 智能体可自动发现调用，无需解析 CLI 用法。

### 脚本总览

| 脚本 | 阶段 | 功能 | 输出格式 |
|------|------|------|---------|
| `scripts/arch_scan.py` | 阶段一 | 目录扫描、入口检测、技术栈识别、文档定位 | JSON / 人类可读 |
| `scripts/dep_graph.py` | 阶段一 | 依赖图生成（Mermaid/DOT），循环依赖检测 | JSON / Mermaid / DOT |
| `scripts/risk_diagnose.py` | 阶段二 | R1-R6 六种衰退风险扫描，四段式发现 | JSON / 人类可读 |
| `scripts/quality_metrics.py` | 阶段三 | MI/CC/HV/健康分计算，热点识别 | JSON / 人类可读 |
| `scripts/regression_guard.py` | 阶段五 | 测试基线记录、回归对比、EvoScore 计算 | JSON / 人类可读 |
| `scripts/mcp_server.py` | Level 3 | MCP 协议服务器（FastMCP，stdio 传输） | MCP 工具 |

### 支持的语言

| 语言 | 扩展名 | 导入解析 | 圈复杂度 | 函数抽取 |
|------|--------|---------|---------|---------|
| Python | .py | ast 模块 | ast 遍历 | ast.FunctionDef |
| Go | .go | import 解析 | 正则 + 大括号匹配 | func 关键字 |
| C/C++ | .c .h .cpp .hpp | #include 解析 | 正则 + 大括号匹配 | 函数签名匹配 |
| Rust | .rs | use/mod 解析 | 正则 + 大括号匹配 | fn 关键字 |
| TypeScript | .ts .tsx | import/from 解析 | 正则 + 大括号匹配 | 函数 / 箭头函数 |
| JavaScript | .js .jsx | import/require 解析 | 正则 + 大括号匹配 | 函数 / 箭头函数 |

### 智能体调用模式（AI Agent Invocation）

智能体在执行各阶段时直接调用脚本获取量化数据，例如：

```bash
# 阶段一：架构感知
python3 scripts/arch_scan.py --target ./src --json
python3 scripts/dep_graph.py --target ./src --json

# 阶段二：风险诊断
python3 scripts/risk_diagnose.py --target ./src --json

# 阶段三：质量度量
python3 scripts/quality_metrics.py --target ./src --json

# 阶段五：回归防护
python3 scripts/regression_guard.py record --output baseline.json --test-cmd "pytest -q"
python3 scripts/regression_guard.py compare --baseline baseline.json --current current.json --json
python3 scripts/regression_guard.py evoscore --history history.json --gamma 1.5
```

### MCP 插件工具（Level 3）

| MCP 工具 | 阶段 | 对应 CLI | 只读 | 幂等 |
|----------|------|---------|------|------|
| `arch_optimize_scan` | 阶段一 | arch_scan.py | 是 | 是 |
| `arch_optimize_dep_graph` | 阶段一 | dep_graph.py | 是 | 是 |
| `arch_optimize_risk_diagnose` | 阶段二 | risk_diagnose.py | 是 | 是 |
| `arch_optimize_quality_metrics` | 阶段三 | quality_metrics.py | 是 | 是 |
| `arch_optimize_regression_guard` | 阶段五 | regression_guard.py | 否 | 否 |

**MCP 配置**（Reasonix/Claude/TRAE 通用）：

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

Reasonix 项目级配置：写入项目根 `.mcp.json`；全局配置写入 Reasonix `config.toml` 的 `[[plugins]]` 段。

### 三级演进路径

| 级别 | 形式 | 调用方式 | 版本 |
|------|------|---------|------|
| Level 1 | 纯文档 | AI 先读文档再手动分析 | v1.0 |
| Level 2 | 脚本增强 | 带 JSON 输出的 CLI 命令 | v2.0 |
| Level 3 | MCP 插件 | 结构化工具的直接 MCP 协议调用 | v3.0 |

### 质量门禁规则（Quality Gate）

| 门禁 | 阈值 | 类型 | 失败行为 |
|------|------|------|---------|
| 零退化率 | = 100% | 硬 | 阻止 PR 合并 |
| 健康分 | >= 70 | 软 | 警告 + 需人工批准 |
| 发布健康分 | >= 80 | 硬 | 阻止发布 |
| 新代码 MI | >= 15 | 硬 | 阻止 PR 合并 |
| 圈复杂度 | <= 15 | 硬 | 阻止 PR 合并 |
| 循环依赖 | = 0 | 硬 | 阻止 PR 合并 |
| 性能回归 | < 10% | 软 | 警告 + 需解释 |

### 设计原则

1. **演进优于快照**：代码质量不是单一状态而是随时间变化的轨迹（SWE-CI 核心洞见）
2. **诊断先于修复**：完成风险诊断前绝不提出修复建议（brooks-lint 铁律）
3. **增量优于大规模**：每次迭代最多 5 个改进需求（SWE-CI 架构师模式）
4. **零退化容忍**：破坏现有功能成本 > 增加新功能（EvoScore 非对称设计）
5. **分工优于全知**：架构师管战略、程序员管执行，避免上帝视角（SWE-CI 双智能体）
6. **量化优于直觉**：MI、健康分、EvoScore 提供客观基线
7. **假阳性防护**：避免把正常设计模式误判为违规
8. **可执行优于纯文档**：所有理论公式与检测规则都有对应脚本实现（v2.0 升级）
9. **协议优于命令行**：MCP 插件封装使工具可被任何 AI 智能体经标准协议发现调用（v3.0 升级）

## 游戏开发技能（v2.2 合并 - Game-Dev Sub-Skill）

本技能合并游戏开发技能，插件默认整合。游戏项目遵循与软件项目相同的工程责任哲学，但增加游戏特有的约定。

### Godot MCP 集成（v2.3 新增）

本技能集成 **Meow Godot MCP**（MIT 授权，零依赖 C++ GDExtension），实现 AI 对 Godot 编辑器的直接控制。

**Godot MCP 架构**：
```
AI Client (Claude/Cursor/Trae)
    ↕ stdio (JSON-RPC 2.0)
Bridge 可执行文件 (~50KB, godot-mcp-bridge.exe)
    ↕ TCP localhost:6800
GDExtension 插件 (Godot 进程内)
    ↕ Godot API
Godot 编辑器 ↔ 运行中的游戏
```

**为什么需要 Bridge？** GDExtension 是 Godot 进程内的共享库，无法被 AI 客户端直接作为子进程启动，且共享 Godot 的 stdout。Bridge 作为轻量级中继解决了这两个问题。

**Godot MCP 工具清单（50 个工具，覆盖完整编辑器 + 游戏运行时工作流）**：

| 类别 | 工具 | 说明 |
|------|------|------|
| 场景操作 | `get_scene_tree` | 获取当前场景树结构 |
| 场景操作 | `create_node` | 创建新节点（支持撤销） |
| 场景操作 | `set_node_property` | 设置节点属性 |
| 场景操作 | `delete_node` | 删除节点（支持撤销） |
| 脚本管理 | `read_script` / `write_script` / `edit_script` | 读写编辑 GDScript |
| 脚本管理 | `attach_script` / `detach_script` | 附加/分离脚本 |
| 项目查询 | `list_project_files` / `get_project_settings` | 项目文件与设置 |
| 运行时控制 | `run_game` / `stop_game` | 启动/停止游戏 |
| 运行时控制 | `get_game_output` | 获取游戏日志（支持过滤） |
| 信号管理 | `get_node_signals` / `connect_signal` / `disconnect_signal` | 信号管理 |
| 场景文件 | `save_scene` / `open_scene` / `create_scene` | 场景文件管理 |
| UI 系统 | `set_layout_preset` / `set_theme_override` / `create_stylebox` | UI 操作 |
| 动画系统 | `create_animation` / `add_animation_track` / `set_keyframe` | 动画控制 |
| 视口截图 | `capture_viewport` | 编辑器 2D/3D 视口截图 |
| **游戏桥接** | **`inject_input`** | **向运行中的游戏注入输入** |
| **游戏桥接** | **`capture_game_viewport`** | **捕获运行中游戏的视口截图** |
| **游戏桥接** | **`click_node`** | **按路径点击运行中游戏的 UI** |
| **运行时查询** | **`get_game_node_property`** | **读取运行中游戏的节点属性** |
| **运行时查询** | **`eval_in_game`** | **在运行中的游戏执行 GDScript 表达式** |
| **集成测试** | **`run_test_sequence`** | **执行测试步骤序列并断言** |
| TileMap | `set_tilemap_cells` / `erase_tilemap_cells` | TileMap 操作 |
| 碰撞形状 | `create_collision_shape` | 一步创建碰撞形状 |
| 编辑器控制 | `restart_editor` | 重启编辑器 |

**加粗**的工具为漏洞挖掘阶段使用的关键工具。

**安装方式**：
1. 自动安装：`wf.ps1 godot-mcp install <project-path>`（自动下载 v1.6 Windows 包）
2. 手动安装：从 [GitHub Releases](https://github.com/MeowMeowZi/meow-godot-mcp/releases) 下载对应平台 zip，解压到 Godot 项目根目录
3. 在 Godot 中启用插件：项目设置 → 插件 → Godot MCP Meow ✔

**配置方式**：
- Godot 编辑器右下角 Dock 面板点击「配置 Claude Code MCP」按钮
- 或手动添加 `.mcp.json` 配置：`wf.ps1 godot-mcp configure`
- 桥接默认连接 `localhost:6800`

**漏洞挖掘时的 Godot 测试流程**（MCP 每次调用时执行）：
1. **启动游戏**：通过 `run_game` 工具启动（自动等待桥接连接）
2. **等待加载**：5s 等待游戏初始化
3. **检查运行时错误**：通过 `get_game_output` 获取错误日志（level=error 过滤）
4. **捕获截图**：通过 `capture_game_viewport` 获取游戏运行状态截图
5. **关闭编辑器**：通过 `stop_game` 工具停止游戏
6. **生成报告**：分析错误日志，生成 bug 报告到 wf-reports/

**规则**：
- 非架构运行时错误不影响流程继续（仅记录报告）
- 架构相关的运行时错误（如 Null 实例、脚本崩溃）记录为 Warning
- 所有 Godot MCP 调用通过 workflow CLI 统一管理

### 游戏项目结构强制约定

```
<game-project>/          # 与软件项目同一文件夹，无例外
├── src/                 # 源代码
│   ├── engine/          # 引擎核心（可复用）
│   ├── game/            # 游戏逻辑（可热更新）
│   └── plugins/         # 插件（默认合并，不单独成项目）
├── bin/                 # 编译产物
│   ├── debug/           # 调试构建
│   └── release/         # 发布构建
├── assets/              # 资源文件
│   ├── raw/             # 原始资源（PSD、FBX、WAV）
│   └── processed/       # 处理后资源（PNG、GLTF、OGG）
├── docs/                # 游戏设计文档
└── tests/               # 测试
```

### 游戏开发原则
- **引擎与游戏逻辑分离**：引擎可复用，游戏逻辑可热更新，不混在一起
- **资源管线自动化**：raw → processed 必须有构建脚本，不允许手动处理
- **性能预算先行**：每帧时间预算、内存预算、绘制调用预算，写在项目文档里
- **数据驱动设计**：游戏参数以配置文件驱动，不硬编码在代码中
- **插件默认合并**：游戏插件不单独成项目，合并到根项目的 src/plugins/ 下

### 游戏项目中的六大衰退风险
- 游戏逻辑的认知过载（R1）比普通代码更致命——一个复杂的状态机可能让整个团队无法维护
- 游戏资源的变更传播（R2）——改一个材质可能影响所有引用它的对象
- 游戏数值配置的重复（R3）——同一个数值在多个地方硬编码
- 游戏引擎的偶发复杂性（R4）——用引擎 5% 的能力解决 80% 的问题就够了
- 游戏模块的依赖失序（R5）——UI 模块不能依赖战斗模块的内部实现
- 游戏设计文档的领域模型扭曲（R6）——代码中的"技能"必须与设计文档中的"技能"一致

### 与 arch-optimize 主流程的协同
- 游戏项目同样适用全部七阶段流程
- 阶段零额外检查游戏资源目录结构
- 阶段三额外度量游戏性能指标（帧率、内存、加载时间）
- 游戏 AI 味检测增加"游戏假实现"（如用占位符模型冒充最终资源）

## 文档模板：技术方向与实现愿景（v2.2 新增）

每个项目文档必须包含"技术方向"和"实现愿景"两个核心章节，回答以下问题：

### 技术方向

```
技术方向：回答"我打算用什么技术路线来实现这个工程"

必须包含：
  1. 核心技术选型：语言、框架、引擎、库
  2. 架构风格：如 ECS、分层、事件驱动
  3. 关键算法/技术：如 Motion Matching、SPH、稀疏体素
  4. 技术理由：为什么选这个而不是其他
  5. 技术风险：这个路线可能出什么问题
```

### 实现愿景

```
实现愿景：回答"这个工程至少要实现什么，呈现哪里"

必须包含：
  1. 核心功能：至少实现什么功能（MVP 定义）
  2. 呈现方式：结果呈现在哪里（命令行、GUI、网页、游戏窗口）
  3. 交互方式：用户怎么使用/操作这个工程
  4. 演示场景：至少能在什么场景下展示
  5. 验收标准：什么算"做完了"
```

### 示例

```
# 项目：自定义游戏引擎

## 技术方向
- 使用 Rust + wgpu（GPU 渲染），纯 ECS 架构
- 稀疏体素八叉树作为场景数据结构
- 基于 Motion Matching 的角色动画系统
- 原因：Rust 零成本抽象 + wgpu 跨平台，体素结构适合大规模场景
- 风险：Motion Matching 的内存占用可能较大，需要 LOD 策略

## 实现愿景
- 核心功能：至少能加载一个体素场景，控制角色在其中行走
- 呈现方式：原生窗口（Windows），OpenGL/Vulkan 后端
- 交互方式：WASD 移动 + 鼠标视角
- 演示场景：一个 256×256 的体素地形，角色可在上面行走
- 验收标准：FPS ≥ 60，加载时间 < 5s，无崩溃
```

**铁律：没有技术方向和实现愿景的文档，不予通过工程前置检查（阶段零）。**

## 引用的基础设施

本技能引用以下基础设施，确保工程质量和开发效率：

| 基础设施 | 用途 | 来源 |
|---------|------|------|
| MCP Codebase-Memory | 代码知识图谱，索引整个仓库用于搜索/影响分析 | [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) |
| aether-trae-bridge | IDE 自动补全 + 代码 RAG，42 个工具 | [bfxh/aether-trae-bridge](https://github.com/bfxh/aether-trae-bridge) |
| **Godot MCP (Meow)** | **Godot 编辑器/游戏运行时控制，50 个 MCP 工具** | [MeowMeowZi/meow-godot-mcp](https://github.com/MeowMeowZi/meow-godot-mcp) |
| **Workflow CLI** | **do→scan→continue 循环 + MCP 统一调用** | `scripts/wf.ps1`（本技能内置） |

**配置方式**：全局 `C:\Users\lbx13\AppData\Roaming\reasonix\config.toml` 或项目级 `.mcp.json`

### Workflow CLI 使用

本技能内置 `scripts/wf.ps1` 工具，实现大规模开发的 do→scan→continue 循环：

```powershell
# 扫描 bug（非架构 bug 不停止流程）
.\scripts\wf.ps1 scan-bugs D:\开发\VoxelForge

# 挖漏洞（直接调用 codebase-memory + aether-bridge + godot-mcp）
.\scripts\wf.ps1 vuln-hunt D:\开发\VoxelForge

# Godot 游戏测试（MCP 启动游戏→检查bug→关闭编辑器）
.\scripts\wf.ps1 godot-test D:\开发\VoxelForge

# 持续循环（每 60s 扫描一次，每 3 次挖一次漏洞）
.\scripts\wf.ps1 loop D:\开发\VoxelForge -interval 60

# 安装 Godot MCP
.\scripts\wf.ps1 godot-mcp install D:\开发\VoxelForge

# 综合安全审计（一键执行全部安全检测）
.\scripts\wf.ps1 audit D:\开发\VoxelForge

# 安全加固（根据审计结果自动修复）
.\scripts\wf.ps1 hardening D:\开发\VoxelForge
```

## 质量门禁（统一）

交付前必须同时满足以下所有条件：

| 门禁 | 阈值 | 来源 |
|------|------|------|
| 健康分 | ≥ 70 | 阶段三 |
| 零退化率 | = 100% | 阶段五 |
| 新增代码 MI | ≥ 15 | 阶段三 |
| 无新增循环依赖 | 0 项 | 阶段二 R5 |
| **AI味 Blocker 计数** | **= 0** | **阶段六** |
| **AI味 Critical 计数** | **= 0** | **阶段六** |
| **文本 AI 味命中** | **= 0** | **阶段六** |

**任何一项不达标 = 禁止交付。** 特别是 AI味 Blocker（假实现/幻觉API）和 Critical（死代码/占位符/虚假错误处理）零容忍。

## 详细参考文档

| 文档 | 内容 |
|------|------|
| `references/architecture-principles.md` | Clean Architecture、SOLID、DDD、六大衰退风险、假阳性防护 |
| `references/coding-conventions.md` | C/C++/Rust/Go/TypeScript 编码规范、错误处理、命名约定 |
| `references/quality-metrics.md` | MI 公式、EvoScore 演进评分、健康分、Pain×Spread 矩阵、ai_flavor_score、SQALE 技术债 |
| `references/regression-guard.md` | 零退化率、回归检测模式、非对称评分、CI 门禁配置、AI味门禁 |
| `references/collaboration-workflow.md` | 架构师-程序员分工、信息隔离、增量优化策略、反馈循环 |
| `references/ai-patterns-catalog.md` | 18 个 AI 味模式详细描述、真实示例（坏 vs 好）、检测方法、修复指南 |
| `references/engineering-responsibility.md` | **v2.1 新增**：工程责任理念、项目结构约定、游戏开发约定、与所有 skill 的协同 |
| `references/aaa-quality-protocol.md` | **v3.0 整合（官方）**：AAA 级视觉质量保障协议，子代理分发与严格批评家迭代循环 |

## 输出格式

每次执行后产出结构化报告：

```markdown
# 架构优化 + AI味净化报告

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
| ai_flavor_score | 35 | 0 | Critical |
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

## 6. AI味净化结果
### 代码 AI 味
- Blocker: 0 项 ✓
- Critical: 2 项（DEAD-001 死代码 ×1, DEAD-008 虚假错误处理 ×1）
- Warning: 5 项
- ai_flavor_score: 35/100

### 文本 AI 味
- TEXT-001 套话开头: 1 处（已修复）
- TEXT-006 信息空洞: 0 处 ✓

### 行为 AI 味
- BEHAV-001 模型骄傲: 0 处 ✓
- BEHAV-002 指鹿为马: 0 处 ✓

## 7. 交付门禁
| 门禁项 | 状态 |
|--------|------|
| 健康分 >= 70 | ✓ PASS |
| 零退化率 = 100% | ✓ PASS |
| AI味 Blocker = 0 | ✓ PASS |
| AI味 Critical = 0 | ✗ FAIL (2 项) |
| 文本 AI 味 = 0 | ✓ PASS |

**结论：禁止交付，需先修复 2 项 AI味 Critical（死代码 + 虚假错误处理）**
```

## 与其他技能的协同

| 场景 | 推荐技能组合 |
|------|-------------|
| 全面架构审查 + AI味检测 | arch-optimize（本技能，全流程含阶段六）|
| 快速 AI 味检测（不做架构分析）| anti-ai-flavor 单独调用 |
| PR 代码审查 | arch-optimize（阶段二 + 阶段六）|
| 技术债路线图 | arch-optimize（阶段三）|
| 发布前健康检查 | arch-optimize（全流程，七阶段全跑）|
| 编码前决定写多少 | ponytail（懒人模式，7级阶梯）|
| 游戏项目全流程 | arch-optimize（含 game-dev 子技能，插件默认合并）|
| 舆论/政治议题分析 | opinion-system（系统性论证，多重后手）|
| 漏洞挖掘 + MCP 安全 | vuln-hunting（含 MCP 协议漏洞）|
| 文档撰写 | doc-writing-guide（含技术方向+实现愿景模板）|
| 项目输出验收 | arch-optimize（阶段六作为最后一道关卡）|

## 设计理念

1. **演进优于快照**：代码质量不是单次状态，而是随时间变化的轨迹（SWE-CI 核心洞察）
2. **诊断先于修复**：在完成风险诊断前绝不提出修复建议（brooks-lint 铁律）
3. **增量优于大规模**：每次最多5个改进需求，小步快跑（SWE-CI 架构师模式）
4. **回归零容忍**：破坏现有功能的代价 > 增加新功能的收益（EvoScore 非对称设计）
5. **分工优于全能**：架构师管战略，程序员管执行，避免上帝视角（SWE-CI 双智能体）
6. **量化优于直觉**：MI、健康分、EvoScore、ai_flavor_score 提供客观基线
7. **假阳性防护**：避免将设计模式正常用法误判为违规
8. **AI味零容忍**（v2.0）：假实现/占位符/指鹿为马 = 欺骗用户，构成 Blocker，禁止交付
9. **诚实优先**（v2.0）：宁可承认做不到，不用占位符冒充。做不到就明确告知用户当前能力边界
10. **人类视角**（v2.0）：以"人类开发者看到这段代码/文本会怎么想"为判断标准——如果他一眼能看出是 AI 糊弄的，就是 AI 味
11. **工程>项目>其他**（v2.2）：工程层级决定项目成败，项目层级决定其他一切。先搭好工程结构，再谈业务
12. **src/bin 分离是铁律**（v2.2）：所有软件/游戏项目必须在同一文件夹内分 src/ 和 bin/，无例外
13. **游戏插件默认合并**（v2.2）：插件不单独成项目，合并到根项目的 src/plugins/ 下
14. **文档必须有方向**（v2.2）：每个项目文档必须包含技术方向和实现愿景，否则不予通过前置检查
