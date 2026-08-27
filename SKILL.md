---
name: "arch-optimize"
description: "架构优化技能 v3.2：六大衰退风险扫描（R1-R6）、质量度量（MI/CC/健康分）、回归防护。五阶段工作流配 4 个零依赖本地脚本（arch_scan/dep_graph/risk_diagnose/quality_metrics/regression_guard），全部输出 JSON。在架构审查、技术债评估、代码重构、质量提升、工程结构评审时调用。"
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

### 阶段二：风险诊断 R1-R6（risk_diagnose）

```bash
python scripts/risk_diagnose.py --target <项目> --json
```

| 编号 | 风险 | Critical 阈值 |
|------|------|--------------|
| R1 | 认知过载 | 函数>50 行；嵌套>5 层 |
| R2 | 变更传播 | 触及>5 文件 |
| R3 | 知识重复 | 同一决策跨 3+ 模块重复 |
| R4 | 偶发复杂性 | 圈复杂度>15 |
| R5 | 依赖失序 | 存在循环依赖 |
| R6 | 领域模型扭曲 | 贫血模型 |

每条发现四段式：**Symptom → Source → Consequence → Remedy**。
假阳性防护（组合根装配≠DIP 违规、DTO≠贫血模型等）见 `references/architecture-principles.md`。

**铁律：完成风险诊断前，绝不提出修复建议。**

### 阶段三：质量度量（quality_metrics）

```bash
python scripts/quality_metrics.py --target <项目> --json
```

MI / 圈复杂度 CC / 逻辑行 LOC / 健康分 = 100 - 15×Critical - 5×Warning - 1×Suggestion。

### 阶段四：增量优化（方法论）

在架构师约束下执行增量改进：每次最多 5 个需求，小步快跑。
完整双智能体流程与需求文档规范见 `references/collaboration-workflow.md`，编码执行标准见 `references/coding-conventions.md`。

### 阶段五：回归防护（regression_guard）

```bash
python scripts/regression_guard.py record --output <基线.json>
python scripts/regression_guard.py compare --baseline <基线.json> --current <当前.json> --json
```

某测试变更前通过、变更后失败 = 回归 = Critical。非对称评分：质量下降比提升惩罚更重。

## 按需加载索引

脚本给出数据，判定规则按需读对应参考文档：

| 场景 | 读这份 |
|------|--------|
| 判定 DIP/ADP/SOLID 违规与假阳性防护 | `architecture-principles.md` |
| 设计架构师需求文档、程序员实现循环 | `collaboration-workflow.md` |
| 具体语言编码标准（C/C++/Go/Rust/TS） | `coding-conventions.md` |
| MI 公式细节与技术债 Pain×Spread 排序 | `quality-metrics.md` |
| 基线记录与非对称评分细则 | `regression-guard.md` |
| 新项目工程结构（src/bin 强制规范） | `engineering-responsibility.md` |

## 质量门禁

交付前必须同时满足：

| 门禁 | 阈值 | 来源 |
|------|------|------|
| 健康分 | ≥ 70 | 阶段三 |
| 零退化率 | = 100% | 阶段五 |
| 新增代码 MI | ≥ 15 | 阶段三 |
| 无新增循环依赖 | 0 项 | 阶段二 R5 |

## 脚本工具集

| 脚本 | 阶段 | 说明 |
|------|------|------|
| `arch_scan.py` | 一 | 目录树、入口点、技术栈 |
| `dep_graph.py` | 一 | 依赖图（Mermaid/DOT）、环检测 |
| `risk_diagnose.py` | 二 | R1-R6 四段式发现 |
| `quality_metrics.py` | 三 | MI/CC/HV/健康分 |
| `regression_guard.py` | 五 | 基线记录与对比 |

全部 Python 3.8+ 标准库零依赖，输出结构化 JSON，Windows 下自动强制 UTF-8 输出。

## 协同

以下能力已拆分为独立技能，不再属于本仓库职责：

- `anti-ai-flavor`：AI 味检测专项（detect_code_ai / detect_text_ai）
- `vuln-hunting`：安全扫描与漏洞挖掘（vuln-scan.ps1 / wf.ps1）
- `project-launcher`：新项目元编排
