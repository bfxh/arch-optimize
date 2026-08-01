# AI味模式目录 (AI Flavor Patterns Catalog)

## 概述

本文档详细描述 anti-ai-flavor 技能检测的 18 个模式，按代码（DEAD-001~010）、文本（TEXT-001~008）、行为（BEHAV-001~005）三类组织。每个模式包含：症状、坏示例、好示例、检测方法、修复指南。

**严重性等级说明：**

| 等级 | 含义 | 处置要求 |
|------|------|----------|
| Blocker | 最高级别，阻止交付 | 必须修复，否则禁止交付 |
| Critical | 严重问题 | 强烈建议修复 |
| Warning | 警告级别 | 建议修复 |

---

## 一、代码反AI味模式（10个）

### DEAD-001 死代码

- **症状**：未使用的函数、变量、import、类
- **严重性**：Critical
- **坏示例**：

```python
import os          # 从未使用
import sys         # 从未使用
from collections import defaultdict  # 从未使用

def helper_function(data):
    """一个从未被调用的辅助函数"""
    result = data.strip()
    return result

UNUSED_CONSTANT = 42  # 从未引用

def main():
    actual_logic()
```

- **好示例**：

```python
def main():
    actual_logic()
```

- **检测方法**：AST 分析未引用的顶层定义；import 扫描
- **修复指南**：删除未使用代码，或标注 `# intentionally kept for future use`

---

### DEAD-002 占位符

- **症状**：TODO/FIXME/pass/NotImplemented/"模拟实现"
- **严重性**：Critical
- **坏示例**：

```python
def calculate_score(user_data):
    # TODO: implement this
    pass

def process_payment(amount):
    # FIXME: need real payment logic
    return None

def export_report(data):
    raise NotImplementedError("This feature is not yet implemented")
```

- **好示例**：

```python
def calculate_score(user_data):
    base = user_data["activity_count"] * 10
    bonus = user_data["streak_days"] * 5
    return base + bonus

def process_payment(amount):
    # 当前版本不支持支付，明确告知用户
    raise PaymentNotSupportedError("支付功能尚未接入，请联系管理员")
```

- **检测方法**：正则匹配 TODO/FIXME/pass/NotImplementedError/raise NotImplemented
- **修复指南**：实现真实逻辑；做不到就告知用户

---

### DEAD-003 假实现

- **症状**：内存模拟冒充真实系统、mock 冒充生产代码
- **严重性**：Blocker（最高级）
- **坏示例**：

```python
# 用内存字典冒充数据库
class Database:
    _store = {}
    
    def save(self, key, value):
        self._store[key] = value  # 数据不持久化，重启即丢失
    
    def get(self, key):
        return self._store.get(key)

# 用 sleep 模拟异步操作
async def send_notification(user_id, message):
    await asyncio.sleep(1)  # 假装在发送
    return True  # 假装发送成功
```

- **好示例**：

```python
# 真实数据库连接
class Database:
    def __init__(self, connection_string):
        self.conn = psycopg2.connect(connection_string)
    
    def save(self, key, value):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kv_store (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value)
            )
        self.conn.commit()

# 真实异步操作
async def send_notification(user_id, message):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{NOTIFICATION_URL}/send",
            json={"user_id": user_id, "message": message}
        )
        response.raise_for_status()
        return True
```

- **检测方法**：检测 "mock"/"fake"/"simulated"/"in-memory" 等关键词与生产代码路径的混用
- **修复指南**：必须用真实实现，禁止用 mock 冒充

---

### DEAD-004 过度注释

- **症状**：注释说明显而易见的事
- **严重性**：Warning
- **坏示例**：

```python
i += 1  # i加1
count = 0  # 初始化变量
result = a + b  # 将a和b相加得到结果
for item in items:  # 遍历items列表
    process(item)  # 处理每个item
```

- **好示例**：

```python
i += 1
count = 0
result = a + b
for item in items:
    process(item)
```

- **检测方法**：注释行与下一行代码的相似度分析
- **修复指南**：删除无用注释，只在复杂逻辑处加注释

---

### DEAD-005 无意义命名

- **症状**：data1/temp/foo/bar/stuff/thing
- **严重性**：Warning
- **坏示例**：

```python
def process_data(data1, data2):
    temp = []
    for stuff in data1:
        thing = do_something(stuff)
        temp.append(thing)
    return temp

def func1(x):
    result1 = x * 2
    result2 = x + 10
    return result1, result2
```

- **好示例**：

```python
def parse_config(raw_config, default_config):
    parsed_entries = []
    for entry in raw_config:
        normalized = normalize_entry(entry)
        parsed_entries.append(normalized)
    return parsed_entries

def scale_and_offset(value, scale_factor, offset):
    scaled = value * scale_factor
    offset_value = value + offset
    return scaled, offset_value
```

- **检测方法**：正则匹配常见无意义名称（data\d?/temp\d?/foo/bar/stuff/thing/func\d?/var\d?）
- **修复指南**：用描述性名称替代

---

### DEAD-006 过度工程化

- **症状**：不必要的抽象层、过度泛化、YAGNI违反
- **严重性**：Warning
- **坏示例**：

```python
# 为单一实现创建抽象接口+工厂+策略模式
from abc import ABC, abstractmethod

class DataProcessorInterface(ABC):
    @abstractmethod
    def process(self, data): pass

class DataProcessorStrategy(DataProcessorInterface):
    def process(self, data):
        return [d * 2 for d in data]

class DataProcessorFactory:
    @staticmethod
    def create_processor() -> DataProcessorInterface:
        return DataProcessorStrategy()

# 实际只有一个实现，永远不会出现第二个
processor = DataProcessorFactory.create_processor()
result = processor.process([1, 2, 3])
```

- **好示例**：

```python
def process_data(data):
    return [d * 2 for d in data]

result = process_data([1, 2, 3])
# 当有第二个实现时再抽象
```

- **检测方法**：检测只有一个实现的接口/抽象类
- **修复指南**：删除不必要的抽象，有第二个实现时再抽象

---

### DEAD-007 重复模式

- **症状**：AI常生成的重复 try-catch/if-else 结构
- **严重性**：Warning
- **坏示例**：

```python
def fetch_user(user_id):
    try:
        response = requests.get(f"{API}/users/{user_id}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error: {e}")
        return None

def fetch_post(post_id):
    try:
        response = requests.get(f"{API}/posts/{post_id}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error: {e}")
        return None

def fetch_comment(comment_id):
    try:
        response = requests.get(f"{API}/comments/{comment_id}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error: {e}")
        return None
```

- **好示例**：

```python
def fetch_resource(resource_type, resource_id):
    try:
        response = requests.get(f"{API}/{resource_type}/{resource_id}")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching {resource_type}/{resource_id}: {e}")
        return None

# 或提取为装饰器
def handle_api_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            return None
    return wrapper
```

- **检测方法**：AST 结构相似度分析
- **修复指南**：提取公共逻辑为装饰器或公共函数

---

### DEAD-008 虚假错误处理

- **症状**：catch了异常但不处理（空catch/只打印）
- **严重性**：Critical
- **坏示例**：

```python
def save_data(data):
    try:
        db.save(data)
    except Exception:
        pass  # 异常被吞掉

def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(e)  # 只打印，不处理不传播
        return {}

def parse_input(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None  # 静默返回 None，调用方无法区分空值和错误
```

- **好示例**：

```python
def save_data(data):
    try:
        db.save(data)
    except DatabaseError as e:
        logger.error(f"Failed to save data: {e}")
        raise  # 传播异常让上层处理

def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {path}, using defaults")
        return DEFAULT_CONFIG
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config {path}: {e}")
        raise
```

- **检测方法**：检测空 except 块或只有 print 的 except 块
- **修复指南**：要么处理异常，要么传播异常（raise），禁止吞掉

---

### DEAD-009 幻觉API

- **症状**：调用不存在的API/库函数/方法签名错误
- **严重性**：Blocker
- **坏示例**：

```python
import os
pid = os.get_pid()           # 实际是 os.getpid()

import string
result = string.split_by(",")  # string 模块无此方法

from datetime import datetime
dt = datetime.from_iso("2024-01-01")  # 实际是 fromisoformat

import requests
resp = requests.fetch("https://api.example.com")  # 实际是 get/post
```

- **好示例**：

```python
import os
pid = os.getpid()  # 正确的 API 名称

from datetime import datetime
dt = datetime.fromisoformat("2024-01-01")  # 正确的方法名

import requests
resp = requests.get("https://api.example.com")  # 正确的方法名
```

- **检测方法**：与已知API签名比对（需要语言服务器支持，脚本做基础检测）
- **修复指南**：查文档修正API调用，验证所有API调用真实存在

---

### DEAD-010 拼凑感

- **症状**：代码段之间风格不一致，像是拼接的
- **严重性**：Warning
- **坏示例**：

```python
# 前半段用 camelCase
def getUserData(userId):
    response = makeRequest(userId)
    return response.data

# 后半段用 snake_case
def process_user_data(user_data):
    result = parse_response(user_data)
    return result

# 混用不同风格的字符串格式化
name = "Alice"
greeting1 = "Hello, %s" % name           # %-formatting
greeting2 = "Welcome, {}".format(name)   # str.format
greeting3 = f"Hi, {name}"                # f-string
```

- **好示例**：

```python
# 统一使用 snake_case
def get_user_data(user_id):
    response = make_request(user_id)
    return response.data

def process_user_data(user_data):
    result = parse_response(user_data)
    return result

# 统一使用 f-string
name = "Alice"
greeting = f"Hello, {name}"
welcome = f"Welcome, {name}"
```

- **检测方法**：命名风格一致性分析
- **修复指南**：统一代码风格（命名规范、格式化方式、缩进等）

---

## 二、文本反AI味模式（8个）

### TEXT-001 套话开头

- **症状**："在当今社会""随着技术的发展""众所周知"
- **修复方式**：直接切入主题
- **坏示例**：

> 在当今社会，随着人工智能技术的飞速发展，深度学习已经成为不可忽视的重要领域。众所周知，Transformer 架构的提出极大地推动了自然语言处理的进步。

- **好示例**：

> Transformer 架构在 2017 年提出后，迅速取代 RNN 成为 NLP 的主流模型。

---

### TEXT-002 空泛表述

- **症状**："具有重要意义""值得关注""不可或缺"
- **修复方式**：用具体数据和事实替代
- **坏示例**：

> 这项技术具有重要的意义，值得关注，它在现代系统中不可或缺。

- **好示例**：

> 这项技术将推理延迟从 200ms 降到 15ms，使实时交互成为可能。

---

### TEXT-003 过度结构化

- **症状**：不必要的列表、过多的层次标题
- **修复方式**：按内容自然组织
- **坏示例**：

> 关于变量命名的建议：
>
> 1. 1.1 变量命名的基本原则
>    1. 1.1.1 使用描述性名称
>    2. 1.1.2 避免缩写
>    3. 1.1.3 保持一致性
> 2. 1.2 变量命名的常见问题
>    1. 1.2.1 命名过长
>    2. 1.2.2 命名过短
>    3. 1.2.3 语义不清

- **好示例**：

> 变量命名应使用描述性名称、避免缩写、保持一致性。常见问题是命名过长或过短导致语义不清。

---

### TEXT-004 虚假自信

- **症状**："显然""毫无疑问""必定"
- **修复方式**：标注不确定性
- **坏示例**：

> 显然这种方法更优，毫无疑问它将成为未来的标准。

- **好示例**：

> 在 X 场景下，这种方法的延迟更低（见基准测试数据），但在 Y 场景下的表现尚待验证。

---

### TEXT-005 AI常用短语

- **症状**："让我们深入探讨""值得注意的是""总而言之""综上所述""深入探讨"
- **修复方式**：用自然人类表达
- **完整短语列表**：

| 短语 | 问题 |
|------|------|
| 综上所述 | 总结性套话，直接给结论即可 |
| 总而言之 | 同上 |
| 值得注意的是 | 空泛过渡，直接陈述事实 |
| 让我们深入探讨 | 假装互动，直接展开内容 |
| 深入探讨 | 同上 |
| 不言而喻 | 懒得解释的借口 |
| 毋庸置疑 | 虚假自信 |
| 众所周知 | 套话开头 |
| 众所周知的是 | 同上 |

- **坏示例**：

> 让我们深入探讨一下这个问题。值得注意的是，这种方法有其优势。综上所述，这是一个值得关注的方案。

- **好示例**：

> 这种方法在延迟上有优势（基准数据见下表），但内存占用较高。

---

### TEXT-006 信息空洞

- **症状**：段落看起来很长但实际信息量为零
- **修复方式**：每段必须有实质信息
- **坏示例**：

> 在现代软件开发实践中，代码质量是一个非常重要的话题。良好的代码质量不仅能够提升开发效率，还能够降低维护成本，这对于任何规模的项目都是至关重要的。因此，我们需要重视代码质量，并在日常开发中加以关注。

- **好示例**：

> 代码质量直接影响维护成本。根据 SonarQube 的统计，修复一个生产环境缺陷的成本是开发阶段的 10 倍。

---

### TEXT-007 重复赘述

- **症状**：同一个观点换三种方式说三遍
- **修复方式**：一个观点说一次
- **坏示例**：

> 这项技术非常重要。可以说，这项技术具有重大意义。换句话说，我们不应忽视这项技术的重要性。

- **好示例**：

> 这项技术将推理延迟降低了 87%，值得在生产环境中采用。

---

### TEXT-008 虚假引用

- **症状**：引用不存在的研究/数据/论文
- **修复方式**：只引用真实可验证的来源
- **坏示例**：

> 根据 Smith 等人 2023 年的研究，该方法的准确率达到 99.5%。  <!-- 该论文不存在 -->

- **好示例**：

> 该方法在 ImageNet 数据集上达到 89.5% 的 Top-1 准确率（来源：论文 arXiv:2010.11929）。

---

## 三、行为反AI味模式（5个）

### BEHAV-001 模型骄傲

- **症状**："我已完美实现""这是一个出色的方案""我为你创建了一个优秀的..."
- **修复方式**：如实报告，不加自我评价
- **对应 quality_standards.json**：无直接映射，但与用户"禁止模型骄傲"的要求一致
- **坏示例**：

> 我已经完美地实现了这个功能，这是一个非常出色的解决方案！代码结构清晰，逻辑优雅，你可以放心使用。

- **好示例**：

> 已实现配置解析功能，支持 JSON 和 YAML 两种格式。测试覆盖了正常路径和 3 种异常情况，全部通过。

---

### BEHAV-002 指鹿为马

- **症状**：识别错误但声称正确（原型说成背包）
- **修复方式**：如实报告，不确定时标注
- **对应 quality_standards.json**：P003
- **坏示例**：

> （图片中是一个背包）这是购物车功能的原型设计图。

- **好示例**：

> （图片中是一个背包）这是一张背包的产品图，与购物车功能无关。如果你需要查看购物车原型，请提供正确的图片。

---

### BEHAV-003 声称存在不展示

- **症状**：说"有调研结果"但不展示
- **修复方式**：展示实际内容
- **对应 quality_standards.json**：P004
- **坏示例**：

> 我已经对相关技术做了充分调研，调研结果显示方案 A 更优。请相信我的判断。

- **好示例**：

> 调研了 3 个候选方案，对比如下：
>
> | 方案 | 延迟 | 内存 | 维护成本 |
> |------|------|------|----------|
> | A    | 15ms | 50MB | 低       |
> | B    | 30ms | 30MB | 中       |
> | C    | 8ms  | 80MB | 高       |
>
> 建议选 A，延迟达标且维护成本最低。

---

### BEHAV-004 过度承诺

- **症状**：承诺做不到的事
- **修复方式**：只承诺能做到的
- **坏示例**：

> 这个方案可以 100% 保证系统永不宕机，完全消除所有 bug，并且性能提升 10 倍。

- **好示例**：

> 这个方案可以将平均故障恢复时间从 30 分钟降到 5 分钟，但不能保证零故障。性能预计提升 2-3 倍，具体取决于负载情况。

---

### BEHAV-005 假装理解

- **症状**：没理解用户意图但假装懂了
- **修复方式**：不懂就问
- **坏示例**：

> 用户："帮我优化一下那个东西"
> 回复："好的，我已经完成了优化，效果很好！"  <!-- 根本不知道用户指的是什么 -->

- **好示例**：

> 用户："帮我优化一下那个东西"
> 回复："你提到的'那个东西'具体是指什么？是上次的数据库查询，还是前端渲染逻辑？请明确一下，我好针对性地优化。"

---

## 四、按语言分类的特殊模式

### Python 特有

| 模式 | 说明 | 坏示例 | 好示例 |
|------|------|--------|--------|
| `if __name__ == "__main__"` 下无实际调用 | 入口块为空 | `if __name__ == "__main__": pass` | `if __name__ == "__main__": run()` |
| `__init__.py` 空文件但目录无实际模块 | 假装是包 | 空的 `__init__.py` 且目录内无 `.py` 文件 | 删除无用的 `__init__.py` 或补充实际模块 |

### Go 特有

| 模式 | 说明 | 坏示例 | 好示例 |
|------|------|--------|--------|
| `_ = variable` 忽略错误返回值 | 吞掉错误 | `result, err := DoSomething(); _ = err` | `result, err := DoSomething(); if err != nil { return err }` |
| 空 `interface{}` 滥用 | 放弃类型安全 | `func Process(data interface{}) interface{}` | `func Process(data *Config) (*Result, error)` |

### C/C++ 特有

| 模式 | 说明 | 坏示例 | 好示例 |
|------|------|--------|--------|
| `// TODO: free memory` 但从不 free | 内存泄漏 | `char* buf = malloc(1024); /* TODO: free later */` | `char* buf = malloc(1024); /* ... */ free(buf);` |
| `void*` 泛型滥用 | 放弃类型安全 | `void* process(void* input)` | `Config* process(Input* input)` |

### Rust 特有

| 模式 | 说明 | 坏示例 | 好示例 |
|------|------|--------|--------|
| `unwrap()` 在生产代码中 | 应使用 `?` 或 match | `let value = config.get("key").unwrap();` | `let value = config.get("key").ok_or(ConfigError::MissingKey)?;` |
| `unsafe` 块无安全说明 | 无文档的不安全操作 | `unsafe { *ptr }` | `// SAFETY: ptr is valid and aligned, checked above` `unsafe { *ptr }` |

### TypeScript 特有

| 模式 | 说明 | 坏示例 | 好示例 |
|------|------|--------|--------|
| `any` 类型滥用 | 放弃类型检查 | `function process(data: any): any` | `function process(data: Config): Result` |
| `@ts-ignore` 压制错误 | 隐藏类型错误 | `// @ts-ignore` `const x = unknownFunc()` | 修正类型或使用 `@ts-expect-error` 并注释原因 |

---

## 五、ai_flavor_score 评分体系

### 评分公式

| 严重性等级 | 单处分值 |
|-----------|---------|
| Blocker | 25 分 |
| Critical | 15 分 |
| Warning | 5 分 |

**总分计算**：`ai_flavor_score = min(100, sum(各模式分值))`，封顶 100 分。

### 交付门禁

| 分数区间 | 等级 | 处置 |
|---------|------|------|
| 0 分 | 完美 | 无AI味，可直接交付 |
| 1-20 分 | 轻微 | 可接受，建议修复 Warning |
| 21-50 分 | 中等 | 需修复 Warning |
| 51-100 分 | 严重 | 必须修复 Blocker/Critical |

### 硬性门禁

**Blocker/Critical 计数为 0 方可交付。**

即无论 `ai_flavor_score` 总分为多少，只要存在 Blocker 或 Critical 级别的模式，一律禁止交付，必须先修复。

### 评分示例

**示例 1：**
- 1 个 Blocker（DEAD-003 假实现）
- 2 个 Critical（DEAD-001 死代码、DEAD-008 虚假错误处理）
- 3 个 Warning（DEAD-004、DEAD-005、DEAD-010）

分数 = 25 + 15*2 + 5*3 = 25 + 30 + 15 = 70 分（严重）

门禁状态：**禁止交付**（存在 Blocker 和 Critical）

**示例 2：**
- 0 个 Blocker
- 0 个 Critical
- 4 个 Warning

分数 = 5*4 = 20 分（轻微）

门禁状态：**可交付**（无 Blocker/Critical）

**示例 3：**
- 0 个 Blocker
- 0 个 Critical
- 0 个 Warning

分数 = 0 分（完美）

门禁状态：**可交付**
