# 游戏项目基础设施

## 目录结构

```
infrastructure/game/
├── engines/      — 引擎知识（Godot/Unity/自研引擎）
├── rendering/    — 渲染技术（Vulkan/OpenGL/着色器）
├── physics/      — 物理模拟（SPH/MPM/FEM 稀疏实现）
├── audio/        — 程序化音频
└── assets/       — 资源管理（程序化生成）
```

## 质量标准

- **哲学**：小而大且强
- **真实性**：物理规则驱动系统，加权混合涌现，分层材质体素
- **算法**：稀疏算法实现（SPH/MPM/FEM 可参考但必须稀疏实现）
- **技术选型**：使用最先进/前沿的技术
- **代码语言**：C/C++/Rust 优先

## 禁止行为

1. 用低模球体代替人物 — 最低限度要有正确拓扑
2. 树木像拼积木 — 使用 L-system / 程序化生长
3. 拿一个球说这是人物 — 绝对禁止
4. 用占位符冒充成品 — 宁可不做，不可做差

## 知识获取

当本目录缺少所需知识时，执行知识自动获取协议（见 `knowledge/auto_fetch.md`）：

1. WebSearch 搜索相关技术 + "latest" + "best practices"
2. WebFetch 获取权威来源
3. 组织为结构化文档存入对应子目录
4. 更新 `_index.json` 知识计数

## 关键技术领域

| 领域 | 关键词 | 优先来源 |
|------|--------|---------|
| 物理模拟 | SPH, MPM, FEM, sparse algorithm | 学术论文 + 开源项目 |
| 体素渲染 | voxel rendering, sparse voxel octree | 技术博客 + GitHub |
| Motion Matching | motion matching, animation system | 学术论文 + GDC演讲 |
| 程序化音频 | procedural audio, synth, Godot audio | 官方文档 + 开源项目 |
| 模块化肢体 | modular limb, skeletal animation | 学术论文 + 技术博客 |
