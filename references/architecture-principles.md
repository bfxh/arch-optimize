# 架构原则参考文档

本文档详细定义架构优化技能所依据的架构原则、衰退风险和假阳性防护规则。

---

## 一、Clean Architecture 原则

来源：Robert C. Martin《Clean Architecture》+ brooks-lint 源覆盖矩阵

### 1.1 依赖倒置原则 (DIP)

**规则**：高层业务逻辑不直接导入低层基础设施。

**检测**：
- 领域层 (`domain/`, `internal/`) 直接 import 数据库驱动、HTTP 客户端、文件系统库 = 🔴 Critical
- 领域接口被定义在基础设施层 = 🔴 Critical

**正确做法**：
- 接口定义在领域层，实现在基础设施层
- 通过依赖注入（DI）在组合根装配

### 1.2 无环依赖原则 (ADP)

**规则**：模块/包之间不允许循环依赖。

**检测**：
- A → B → C → A = 🔴 Critical
- 使用 Mermaid 图标注虚线表示循环

**正确做法**：
- 提取共享模块到独立包
- 通过接口反转依赖方向
- 使用事件解耦

### 1.3 稳定依赖原则 (SDP)

**规则**：稳定、广泛使用的组件不应依赖不稳定、频繁变化的组件。

**检测**：
- 核心库依赖实验性模块 = 🟡 Warning
- 公共 API 依赖未稳定 API = 🟡 Warning

### 1.4 稳定抽象原则 (SAP)

**规则**：抽象组件不应依赖具体实现。

**检测**：
- 接口/抽象类导入具体类 = 🔴 Critical

### 1.5 接口隔离原则 (ISP)

**规则**：模块实现了接口但只使用其方法的子集 = 违规。

**检测**：
- 接口方法数 > 7 且消费者只用其中 2-3 个 = 🟡 Warning
- 胖接口强迫调用者承担不需要的依赖 = 🔴 Critical

### 1.6 里氏替换原则 (LSP)

**规则**：子类不得破坏父类行为契约。

**检测**：
- 子类覆盖方法并抛出不兼容异常 = 🔴 Critical
- 子类改变了前置/后置条件 = 🟡 Warning

---

## 二、SOLID 原则（可操作阈值）

### S - 单一职责原则

**检测信号**：
- 一个类因多个不同业务原因变更（如 UserService 同时处理计费、通知、档案）= 🔴 Critical
- 类名包含 "Manager"、"Helper"、"Util" 且方法数 > 10 = 🟡 Warning
- 方法间无内聚性（方法A操作字段a，方法B操作字段b，互不交叉）= 🟡 Warning

**修复方向**：提取独立服务，按业务能力拆分

### O - 开闭原则

**检测信号**：
- 新增类型需要修改 switch/if-else 链 = 🟡 Warning
- 新增支付类型触及日志、缓存、通知代码（非正交）= 🔴 Critical

**修复方向**：策略模式、工厂模式、插件注册表

### L - 里氏替换

**检测信号**：
- 子类方法抛出父类不会抛出的异常 = 🔴 Critical
- 子类忽略父类方法实现（空实现或 throw NotImplemented）= 🟡 Warning

### I - 接口隔离

**检测信号**：
- 接口方法 > 7 个 = 🟡 Warning
- 消费者被迫依赖不需要的方法 = 🔴 Critical

**修复方向**：按消费者角色拆分接口

### D - 依赖倒置

**检测信号**：
- 高层模块 import 低层模块的具体类型 = 🔴 Critical
- 依赖箭头指向不稳定方向 = 🟡 Warning

---

## 三、领域驱动设计 (DDD)

来源：Eric Evans《Domain-Driven Design》

### 3.1 统一语言 (Ubiquitous Language)

**规则**：代码变量/类/方法名必须与业务专家使用的概念一致。

**检测**：
- 同一概念用不同名称（user/account/member/customer 混用）= 🟡 Warning (R3)
- 代码术语与业务文档不一致 = 🟡 Warning

### 3.2 限界上下文 (Bounded Context)

**规则**：跨上下文边界需翻译层或防腐层。

**检测**：
- 计费逻辑出现在用户模块中 = 🔴 Critical (R6)
- 库存概念直接渗透到订单模块（无翻译）= 🟡 Warning

### 3.3 贫血领域模型

**规则**：领域对象应包含行为，而非只有 getter/setter。

**检测**：
- 领域对象只有属性无方法，业务逻辑全在 Service 层 = 🔴 Critical (R6)
- `User` 类只有 `getName()/setName()`，验证逻辑在 `UserService` 中 = 🔴 Critical

**例外（假阳性）**：
- DTO、持久化记录、API 载荷模型允许纯数据结构
- 值对象（Value Object）可以是不可变数据载体

### 3.4 实体 vs 值对象

**规则**：Money、Email、Address 应为不可变值对象。

**检测**：
- Money 类有可变 amount 字段和 setter = 🟡 Warning
- Email 类有 ID 和生命周期 = 🟡 Warning

### 3.5 聚合根

**规则**：跨聚合访问只能通过根。

**检测**：
- 直接查询聚合内部实体（绕过根）= 🔴 Critical
- 聚合内不变量未被保护 = 🟡 Warning

---

## 四、六大衰退风险（R1-R6）

来源：brooks-lint，基于12本经典工程书籍

### R1 认知过载 (Cognitive Overload)

**出处**：Code Complete、Refactoring、DDD、A Philosophy of Software Design

**诊断问题**：理解这段代码需要多少脑力？

**检测阈值**：
| 指标 | Critical | Warning | OK |
|------|----------|---------|-----|
| 函数行数 | >50 | 20-50 | ≤20 |
| 嵌套深度 | >5 | 4-5 | ≤3 |
| 参数数量 | >4 | 3-4 | ≤2 |
| 圈复杂度 | >15 | 11-15 | ≤10 |

**假阳性例外**：
- 线性 + 清晰命名 + 卫语句的长函数 ≠ 认知过载
- 纯数据声明序列（如配置表、测试用例列表）不算

### R2 变更传播 (Change Propagation)

**出处**：Refactoring、Clean Architecture、Pragmatic Programmer、Software Engineering at Google

**诊断问题**：改一处会波及多少不相关的东西？

**检测阈值**：
| 指标 | Critical | Warning | OK |
|------|----------|---------|-----|
| 变更触及文件数 | >5 | 3-5 | ≤2 |
| 模块扇出 (fan-out) | >7 | 5-7 | ≤5 |
| 修改一个概念需改的类数 | >3 | 2-3 | 1 |

### R3 知识重复 (Knowledge Duplication)

**出处**：Pragmatic Programmer（DRY）、Refactoring、DDD

**诊断问题**：同一决策是否在多处表达？

**检测阈值**：
| 指标 | Critical | Warning | OK |
|------|----------|---------|-----|
| 跨模块重复代码块 | ≥3处 | 2处 | 1处 |
| 同一业务规则多处硬编码 | ≥2处 | - | 1处 |
| 魔法数字重复 | ≥3处 | 2处 | 命名常量 |

**假阳性例外**：
- 不同限界上下文间的相似代码 ≠ DRY 违规
- 临时迁移期的重复代码 ≠ 债务

### R4 偶发复杂性 (Accidental Complexity)

**出处**：Refactoring、Code Complete、Brooks（No Silver Bullet）、Philosophy of SD

**诊断问题**：代码是否比它解决的问题更复杂？

**检测信号**：
- 用了设计模式但问题本身不需要 = 🟡 Warning
- 过度抽象（只有一个实现的接口工厂）= 🟡 Warning
- 解决框架限制的 workaround 代码多于业务代码 = 🔴 Critical
- 圈复杂度 > 20 且非算法密集场景 = 🔴 Critical

### R5 依赖失序 (Dependency Disorder)

**出处**：Clean Architecture、Brooks、Pragmatic Programmer、SE@Google

**诊断问题**：依赖是否朝一致、可预测的方向流动？

**检测阈值**：
| 指标 | Critical | Warning |
|------|----------|---------|
| 循环依赖 | 存在 | - |
| 领域层→基础设施层 | 直接依赖 | - |
| 跨层反向引用 | 存在 | - |
| 模块扇入<2且扇出>5 | - | 存在 |

**假阳性例外**：
- 组合根（Composition Root）装配具体依赖不算 DIP 违规
- 薄适配器在显式作为边界胶水时可双向导入
- 稳定外观（Facade）在依赖策略明确时可高扇出

### R6 领域模型扭曲 (Domain Model Distortion)

**出处**：DDD、Refactoring

**诊断问题**：代码是否忠实地表达了要解决的问题？

**检测信号**：
- 模块名与业务词汇不匹配 = 🟡 Warning
- 贫血领域模型（逻辑在 Service，对象纯数据）= 🔴 Critical
- 限界上下文越界（计费逻辑在用户模块）= 🔴 Critical
- 缺少防腐层，外部概念直接渗透领域 = 🟡 Warning

---

## 五、假阳性防护规则

以下情况不应被标记为违规（避免噪音）：

| 场景 | 可能误判为 | 实际是 |
|------|-----------|--------|
| 组合根装配具体依赖 | DIP 违规 | 设计正确 |
| DTO / 持久化记录 / API 载荷纯数据 | 贫血模型 | 数据传输对象 |
| 不同限界上下文间相似代码 | DRY 违规 | 上下文隔离 |
| 临时迁移期重复代码 | 技术债 | 有意桥接 |
| 线性+卫语句+清晰命名的长函数 | 认知过载 | 可接受 |
| 稳定公共 API 的观察行为 | Hyrum 定律债务 | 稳定契约 |
| 薄适配器双向导入 | 依赖失序 | 边界胶水 |
| 测试替身/mock 的结构 | 生产代码违规 | 测试专用 |

**判定流程**：
1. 先检查是否属于假阳性例外列表
2. 如果属于，降级为 🟢 Suggestion 或 dismiss
3. 如果不属于，按正常严重性评级

---

## 六、Conway 定律检查

**规则**：架构是否映射团队结构？

**检测**：
- 跨团队协调是否成为每个功能的成本 = 🟡 Warning
- 模块边界是否与团队边界对齐 = 评估项
- 是否存在"康威逆定律"（人为拆分团队去匹配期望架构）= 评估项

**行动建议**：
- 如果架构与团队结构不匹配，优先调整团队结构而非强制架构
- 参考 Team Topologies 的四种团队类型（流对齐、平台、复杂子系统、赋能）
