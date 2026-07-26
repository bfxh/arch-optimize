# 软件项目基础设施

## 目录结构

```
infrastructure/software/
├── patterns/     — 设计模式（Clean Architecture, SOLID, DDD）
├── testing/      — 测试框架（单元/集成/E2E）
├── ci-cd/        — 持续集成（GitHub Actions, CircleCI）
└── security/     — 安全规范
```

## 质量标准

- **代码质量**：高质量代码，反对智能体生成劣质代码
- **禁止死代码**：禁止死代码、内存模拟、假软件
- **错误处理**：高质量错误报告和调试能力
- **审核要求**：软件项目必须通过审核后智能体才能工作

## 代码语言优先级

1. C / C++ / Rust（优先）
2. TypeScript / Go
3. Python（工具脚本可用）

## 知识获取

当本目录缺少所需知识时，执行知识自动获取协议：

1. WebSearch 搜索相关技术 + "latest" + "best practices"
2. WebFetch 获取权威来源
3. 组织为结构化文档存入对应子目录
4. 更新 `_index.json` 知识计数

## 审核流程

软件项目在智能体开始工作前必须通过审核：

1. 架构审查（arch-optimize 阶段一-三）
2. 代码质量检查（MI >= 15, CC <= 15）
3. 安全审查
4. 审核通过后才能开始编码

## 关键技术领域

| 领域 | 关键词 | 优先来源 |
|------|--------|---------|
| 架构模式 | Clean Architecture, SOLID, DDD, hexagonal | 经典书籍 + 技术博客 |
| 测试 | TDD, integration test, E2E, property test | 官方文档 + 最佳实践 |
| CI/CD | GitHub Actions, CircleCI, automation | 官方文档 |
| 安全 | OWASP, security best practices | OWASP 官方 + 安全博客 |
