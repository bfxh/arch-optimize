# 编码规范参考文档

本文档定义多语言编码规范，作为架构优化阶段四（增量优化）的执行标准。

---

## 一、通用规范（语言无关）

### 1.1 函数规范

| 规则 | 阈值 | 严重性 |
|------|------|--------|
| 函数长度 | ≤50 行 | >50 = Critical |
| 嵌套深度 | ≤3 层 | >5 = Critical |
| 参数数量 | ≤4 个 | >4 = Warning |
| 圈复杂度 | ≤10 | >15 = Critical |
| 单一职责 | 一个函数做一件事 | 违反 = Warning |

### 1.2 命名规范

- **意图揭示**：名字应描述"做什么"而非"怎么做"
- **业务统一语言**：变量/类/方法名与业务专家用语一致
- **避免缩写**：除非是领域通用缩写（如 URL、ID、HTTP）
- **避免匈牙利记号**：不使用类型前缀（如 `strName`、`iCount`）
- **布尔变量**：用 `is/has/can/should` 前缀（如 `isValid`、`hasPermission`）

### 1.3 注释规范

- **解释"为什么"而非"是什么"**：代码应自解释
- **公共 API 必须有文档注释**
- **TODO 必须带 owner 和日期**：`// TODO(owner, 2026-01-15): description`
- **避免注释掉的代码**：用版本控制管理历史

### 1.4 错误处理

- **不忽略错误**：每个错误必须被处理或显式传播
- **错误包装**：传播时添加上下文（文件名、操作名）
- **不滥用异常**：异常用于异常情况，不用于正常控制流
- **快速失败**：参数校验在入口处完成

### 1.5 文件组织

- **一个文件一个主要类型**（C/C++ 的 .h/.c 对除外）
- **文件名与主要类型名一致**
- **import 顺序**：标准库 → 第三方库 → 项目内部 → 当前模块
- **文件长度**：建议 ≤500 行，>1000 行 = Warning

---

## 二、C/C++ 规范

### 2.1 内存管理

```cpp
// ✅ 正确：RAII + 智能指针
std::unique_ptr<Widget> createWidget() {
    return std::make_unique<ConcreteWidget>();
}

// ❌ 错误：裸 new/delete
Widget* w = new Widget();
// ... 忘记 delete
```

**规则**：
- 优先使用 `std::unique_ptr` / `std::shared_ptr`
- 禁止裸 `new`/`delete`（除自定义容器内部实现）
- 禁止 `malloc`/`free`（C++ 代码中）
- 所有权语义清晰：`unique_ptr` = 独占，`shared_ptr` = 共享，`weak_ptr` = 观察
- C 代码中使用 `__attribute__((cleanup))` 或等价机制实现 RAII

### 2.2 const 正确性

```cpp
// ✅ 正确：const 传播
class Container {
public:
    size_t size() const { return items_.size(); }
    const Item& get(size_t i) const { return items_[i]; }
    void add(Item item) { items_.push_back(std::move(item)); }
private:
    std::vector<Item> items_;
};
```

**规则**：
- 不修改对象状态的方法标记 `const`
- 不修改的参数按 `const&` 传递
- 局部变量不修改的标记 `const` 或 `constexpr`
- `const` 成员函数不得调用非 `const` 成员函数

### 2.3 异常安全

**三个保证级别**：
1. **基本保证**：异常时不泄漏资源、不破坏不变量（最低要求）
2. **强保证**：异常时回滚到操作前状态（事务语义）
3. **不抛保证**：`noexcept`，绝不抛异常（析构函数、move 操作）

```cpp
// ✅ 强保证：copy-and-swap
Container& operator=(Container other) noexcept {
    swap(other);
    return *this;
}
```

### 2.4 资源管理

- **RAII 是第一原则**：资源获取即初始化
- 文件、锁、 socket 必须用 RAII 包装
- 禁止 `goto` 资源清理模式（C 代码除外，且需注释说明）
- `std::lock_guard` / `std::scoped_lock` 优先于手动 lock/unlock

### 2.5 模板与泛型

- **概念 (Concepts)** 优先于 SFINAE（C++20+）
- 模板参数名有意义：`template<typename T>` → `template<typename Element>`
- 特化应限于标准库类型适配
- 避免过度模板化（编译时间、错误信息可读性）

### 2.6 C 特定规范

- 用 `struct` 定义纯数据，用 `typedef` 定义函数指针类型
- 头文件保护：`#pragma once` 优先于 `#ifndef` 守卫
- 宏使用最小化，优先 `static inline` 函数
- 可变参数函数需类型检查或使用格式字符串属性

---

## 三、Rust 规范

### 3.1 所有权与借用

```rust
// ✅ 正确：借用而非克隆
fn process(data: &str) -> String {
    data.to_uppercase()
}

// ❌ 不推荐：不必要的克隆
fn process(data: String) -> String {
    data.to_uppercase()
}
```

**规则**：
- 优先借用 `&T` / `&mut T`，避免不必要的 `clone()`
- 所有权转移用 `move` 语义
- 生命周期标注只在编译器无法推断时添加
- `Cow<'_, T>` 用于可能需要也可能不需要拥有的场景

### 3.2 unsafe 隔离

```rust
// ✅ 正确：unsafe 封装在安全 API 后
mod raw_buffer {
    /// 安全的封装，内部使用 unsafe
    pub fn read_at(buf: &[u8], idx: usize) -> Option<u8> {
        if idx < buf.len() {
            Some(buf[idx]) // 编译器已保证安全
        } else {
            None
        }
    }
}
```

**规则**：
- `unsafe` 块最小化，每处必须有 `// SAFETY:` 注释说明不变量
- `unsafe` 封装在模块内部，对外暴露安全 API
- FFI 边界必须有错误处理和资源释放
- 禁止 `unsafe` 用于绕过借用检查器

### 3.3 错误处理

```rust
// ✅ 正确：类型化错误 + ?
#[derive(Debug, thiserror::Error)]
pub enum ParseError {
    #[error("unexpected token: {0}")]
    UnexpectedToken(String),
    #[error("unexpected EOF")]
    UnexpectedEof,
}

pub fn parse(input: &str) -> Result<Ast, ParseError> {
    let tokens = tokenize(input)?;
    parse_ast(&tokens)
}
```

**规则**：
- 使用 `Result<T, E>` 而非 `Option<T>` 表示可恢复错误
- 错误类型使用 `thiserror` 或手动实现 `Error`
- `?` 操作符传播错误，添加上下文用 `.map_err()`
- `panic!` 仅用于不可恢复的程序错误（不变量违反）
- `unwrap()` / `expect()` 仅用于测试或不变量保证的场景

### 3.4 trait 设计

- trait 应小而专注（ISP）
- trait 方法默认实现优先于具体类型要求
- `dyn Trait` 用于运行时多态，`impl Trait` 用于编译时多态
- trait bound 使用 `where` 子句提高可读性

### 3.5 零成本抽象

- 迭代器链编译为等效手写循环
- 泛型单态化无运行时开销
- `enum` 的 `match` 编译为跳转表
- 避免不必要的 `Box<dyn Trait>`，优先泛型

---

## 四、Go 规范

### 4.1 错误处理

```go
// ✅ 正确：错误包装
if err := db.Save(user); err != nil {
    return fmt.Errorf("save user %s: %w", user.ID, err)
}
```

**规则**：
- 错误必须检查，禁止 `_ = err`
- 传播时用 `fmt.Errorf("...: %w", err)` 包装
- 库代码不调 `os.Exit` / `panic`（除非不可恢复）
- 自定义错误类型实现 `Error()` 和 `Unwrap()`
- `errors.Is` / `errors.As` 用于错误判断

### 4.2 包设计

- **单一职责**：一个包做一件事
- **最小导出面**：只导出必要的标识符
- **导入方向无环**：包间不允许循环依赖
- `init()` 仅用于注册（provider/tool 注册），不用于复杂逻辑
- 导出标识符必须有文档注释

### 4.3 并发

- **CSP 模型**：goroutine + channel 优先于共享内存
- **不启动不停止的 goroutine**：必须有退出机制（context/context cancel）
- **channel 关闭**：由发送方关闭，不由接收方关闭
- **select + context**：用于超时和取消
- **sync.Mutex**：用于保护共享状态，锁范围最小化

### 4.4 接口

- **消费者定义接口**：在消费方定义小接口，而非提供方定义大接口
- **接口隔离**：1-3 个方法的接口优于 10+ 方法的接口
- **隐式实现**：Go 不需要 `implements` 关键字
- **避免空接口 `interface{}`**：使用泛型（Go 1.18+）或具体类型

### 4.5 构建

- `CGO_ENABLED=0` 生成静态二进制（可交叉编译）
- `-trimpath` 移除构建路径信息
- `-ldflags="-s -w"` 剥离调试信息（发布构建）
- 模块化设计：独立功能拆分为独立 Go 模块

---

## 五、TypeScript 规范

### 5.1 类型安全

```typescript
// ✅ 正确：判别联合
type Result<T, E> =
    | { status: 'ok'; value: T }
    | { status: 'error'; error: E };

// ❌ 错误：any
function process(data: any): any { ... }
```

**规则**：
- `strict: true` 必须开启
- 禁止 `any`，用 `unknown` + 类型守卫替代
- 禁止 `as` 类型断言（除类型测试文件），用类型守卫替代
- 判别联合（Discriminated Union）优先于可选属性
- Branded types 防止原始类型混淆

```typescript
// Branded type 示例
type UserId = string & { readonly __brand: 'UserId' };
type Email = string & { readonly __brand: 'Email' };
```

### 5.2 不可变优先

```typescript
// ✅ 正确：readonly + 不可变更新
interface Config {
    readonly port: number;
    readonly host: string;
}

function updatePort(config: Config, port: number): Config {
    return { ...config, port };
}
```

**规则**：
- 接口属性默认 `readonly`
- 数组用 `readonly T[]` 而非 `T[]`
- 状态更新用展开运算符或 immer
- 禁止 `let`，优先 `const`
- `Object.freeze` 用于深层不可变

### 5.3 错误处理

- 可恢复错误用 Result 类型（`{ ok: true, value } | { ok: false, error }`）
- 异常用于不可恢复的编程错误
- async 函数必须处理 rejection
- Promise 链必须有 `.catch()` 或 `try/catch`

### 5.4 模块组织

- 一个文件一个主要导出
- `index.ts` 仅用于 re-export，不含逻辑
- barrel file 避免循环依赖
- 类型导入用 `import type { ... }`（tree-shaking）

---

## 六、命名约定速查

| 概念 | C/C++ | Rust | Go | TypeScript |
|------|-------|------|----|-----------|
| 类型/类 | PascalCase | PascalCase | PascalCase | PascalCase |
| 函数 | snake_case | snake_case | PascalCase | camelCase |
| 变量 | snake_case | snake_case | camelCase | camelCase |
| 常量 | UPPER_SNAKE | UPPER_SNAKE | PascalCase | UPPER_SNAKE |
| 文件 | snake_case | snake_case | lowercase | kebab-case |
| 包/模块 | snake_case | snake_case | lowercase | kebab-case |
| 泛型参数 | T, U, K, V | T, U, K, V | T, U, K, V | T, U, K, V |
| 接口 | I前缀(可选) | trait PascalCase | er后缀 | I前缀(不推荐) |

---

## 七、代码审查检查清单

在提交 PR 前，逐项检查：

- [ ] 函数长度 ≤50 行（特殊情况 ≤80 行需注释说明）
- [ ] 嵌套深度 ≤3 层
- [ ] 参数数量 ≤4 个
- [ ] 无魔法数字（用命名常量替代）
- [ ] 命名与业务统一语言一致
- [ ] 错误被处理或传播（不忽略）
- [ ] 错误传播时添加上下文
- [ ] 无注释掉的代码
- [ ] 公共 API 有文档注释
- [ ] 无循环依赖
- [ ] 依赖方向正确（领域→应用→基础设施）
- [ ] 新增测试覆盖变更
- [ ] 测试全部通过（零退化率 = 100%）
