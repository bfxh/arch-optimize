---
name: "arch-optimize"
description: "架构优化技能 v3.1：六大衰退风险扫描（R1-R6）、架构师-程序员双智能体协作、反AI味检测、src+bin 规范、本地脚本工具集（arch_scan/dep_graph/risk_diagnose/quality_metrics/regression_guard/vuln-scan/wf 全本地零依赖输出 JSON）。在架构审查、技术债评估、代码重构、质量提升、AI味检测、工程结构评审时调用。"
version: "3.1"
runAs: subagent
allowed-tools: read_file, write_file, edit_file, grep, glob, bash
---

# 架构优化技能 v3.1（Architecture Optimization + Anti-AI-Flavor + 本地脚本工具集）

## 定位

**根哲学：对工程负责。** 这是本技能以及所有关联 skill 的根本原则。不管什么项目类型（软件、游戏、舆论分析、漏洞挖掘），第一原则是对工程负责——交付的每一行代码、每一份文档、每一个决策，都必须经得起工程检验。

本技能是**架构健康 + 内容真实性 + 工程责任**的三重质量门禁：

1. **六大衰退风险扫描**（brooks-lint，基于 12 本经典工程书籍）：R1-R6 结构化诊断
2. **架构师-程序员双智能体协作**：战略层与执行层分离，避免上帝视角
3. **反AI味检测**：18 个 AI 特有低质量模式扫描，确保交付物经得起人类逐行审视

**v3.1 变化**：剥离全部 MCP 职责描述（MCP 工具是独立配置层，不由技能承担）；技能只保留方法论 + 全本地脚本。

## 调用时机

- 架构审查、技术债评估、代码重构、质量提升、AI味检测、工程结构评审
- 新项目开工（强制 src/ + bin/ 分离）
- 交付前质量门禁（配合 preflight）

## 五大阶段工作流

### 阶段一：架构感知（arch_scan + dep_graph）

```bash
python scripts/arch_scan.py --target <项目> --json
python scripts/dep_graph.py --target <项目> --json
```

- 目录树/文件清单、依赖图（fan_in/fan_out/layer）、模块边界
- 产出：项目结构概览 JSON

### 阶段二：风险诊断 R1-R6（risk_diagnose）

```bash
python scripts/risk_diagnose.py --target <项目> --json
```

六大衰退风险：
| 编号 | 风险 | 检测要点 |
|------|------|----------|
| R1 | 代码重复 | 克隆检测 |
| R2 | 复杂性蔓延 | 圈复杂度/认知复杂度 |
| R3 | 隐藏耦合 | 依赖环、fan 失衡 |
| R4 | 膨胀接口 | 参数过多、方法过长 |
| R5 | 循环依赖 | import 图 DFS 找环 |
| R6 | 死代码 | 定义未引用 |

### 阶段三：质量度量（quality_metrics）

```bash
python scripts/quality_metrics.py --target <项目> --json
```

- 可维护性指数 MI、圈复杂度 CC、逻辑代码行 LOC、健康分
- 阈值：健康分 ≥ 70，新增代码 MI ≥ 15

### 阶段四：反AI味检测（detect_code_ai / detect_text_ai）

```bash
python scripts/detect_code_ai.py --target <项目> --json
python scripts/detect_text_ai.py --target <项目> --json
```

18 个 AI 特有低质量模式：死代码、占位符、套话、过度工程化、模型骄傲、指鹿为马等。代码与文档双通道。

### 阶段五：回归防护（regression_guard）

```bash
python scripts/regression_guard.py record --output <基线.json>
python scripts/regression_guard.py compare --baseline <基线.json> --current <当前.json> --json
```

- 非对称评分惩罚回归：质量下降比提升惩罚更重
- 零退化率 = 100% 方可合并（硬性门禁）

## src/bin 规范（强制）

所有软件/游戏项目必须在同一文件夹内分 `src/` 和 `bin/`：
- `src/`：源代码（手写部分）
- `bin/`：构建产物（自动生成，不手工修改）
- 游戏额外区分 `bin/debug/` 与 `bin/release/`

## 本地脚本工具集

| 脚本 | 用途 | 依赖 |
|------|------|------|
| `arch_scan.py` | 架构感知（目录树/文件清单） | Python 3.8+ 标准库 |
| `dep_graph.py` | 依赖图（fan_in/fan_out/layer） | 同上 |
| `risk_diagnose.py` | R1-R6 风险诊断 | 同上 |
| `quality_metrics.py` | MI/CC/LOC/健康分 | 同上 |
| `regression_guard.py` | 回归检测（基线对比/零退化率） | 同上 |
| `vuln-scan.ps1` | 安全漏洞扫描（7 维度） | PowerShell |
| `detect_code_ai.py` | 代码 AI 味检测 | Python 标准库 |
| `detect_text_ai.py` | 文档 AI 味检测 | 同上 |
| `wf.ps1` | 本地工作流 CLI（do→scan→continue） | PowerShell |

全部**仅使用标准库/系统自带**，零第三方依赖，输出结构化 JSON。

### 安全扫描（vuln-scan.ps1，7 维度）

```powershell
powershell -File scripts/vuln-scan.ps1 -TargetPath <项目> -All
```

| 维度 | 覆盖 |
|------|------|
| GDScript 安全 | 15 种模式（OS.execute/get_node 注入等） |
| Rust 不安全 | 15 种模式（unsafe/unwrap 等） |
| C/C++ 安全 | 10 种检测 |
| MCP 配置审计 | 10 种 |
| 密钥泄露 | 20 种模式 |
| 配置安全 | 敏感配置审计 |
| 依赖审计 | 已知漏洞依赖 |

### Workflow CLI（wf.ps1，本地命令）

```powershell
.\scripts\wf.ps1 scan-bugs <项目>        # 扫描 bug（非架构 bug 不停止流程）
.\scripts\wf.ps1 vuln-hunt <项目>        # 本地漏洞挖掘（vuln-scan.ps1 优先）
.\scripts\wf.ps1 local-scan <项目>       # 本地全量扫描
.\scripts\wf.ps1 audit <项目>            # 综合安全审计
.\scripts\wf.ps1 hardening <项目>        # 安全加固（生成修复建议）
.\scripts\wf.ps1 loop <项目>             # do→scan→continue 循环
```

## 质量门禁（统一）

交付前必须同时满足以下所有条件：

| 门禁 | 阈值 | 来源 |
|------|------|------|
| 健康分 | ≥ 70 | 阶段三 |
| 零退化率 | = 100% | 阶段五 |
| 新增代码 MI | ≥ 15 | 阶段三 |
| 无新增循环依赖 | 0 项 | 阶段二 R5 |
| 无 Critical 安全发现 | 0 项 | vuln-scan |
| 无 AI 味 Blocker | 0 项 | 阶段四 |

## 协同

- `preflight`：多审查器高并发编排（含本技能脚本）
- `vuln-hunting`：安全专项（共享 vuln-scan.ps1 与工程责任哲学）
- `code-review`：7 维本地代码审核管道
- `anti-ai-flavor`：AI 味检测专项
- `game-design` / `game-dev`：游戏项目（沿用本技能 src/bin 规范）
- `ponytail`：写代码前 7 级决策阶梯（YAGNI）

> 注：MCP 工具（codebase-memory / srclight / godot-mcp / ocr-mcp）是独立配置层（config.toml / .mcp.json），不属于本技能职责；本技能只提供方法论与本地脚本。
