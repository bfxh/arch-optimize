# 回归防护参考文档

本文档定义架构优化技能的回归检测、零退化率和非对称评分体系。

---

## 一、回归定义

### 1.1 什么是回归

**回归 (Regression)**：某个测试用例在代码变更前已通过，但在变更后失败。

```
基线状态: test_A ✅  test_B ✅  test_C ❌
变更后:   test_A ❌  test_B ✅  test_C ✅

结果: test_A 发生回归（🔴 Critical）
      test_C 改善（🟢 改进）
```

### 1.2 回归类型

| 类型 | 描述 | 严重性 |
|------|------|--------|
| 功能回归 | 原有功能不再工作 | 🔴 Critical |
| 性能回归 | 原有功能变慢 | 🟡 Warning |
| 兼容性回归 | API/接口行为改变 | 🔴 Critical |
| 安全回归 | 安全属性降低 | 🔴 Critical（阻断） |

---

## 二、零退化率 (Zero Regression Rate)


### 2.1 定义

```
零退化率 = 无回归任务数 / 总任务数 × 100%
```

在整个维护过程中**完全没有破坏原有功能**的任务比例。


| 模型 | 零退化率 | 梯队 |
|------|---------|------|
| Claude-opus-4.6 | 76% | 遥遥领先 |
| Claude-opus-4.5 | 51% | 第二 |
| Kimi-K2.5 | 37% | 第二梯队 |
| GLM-5 | 36% | 第二梯队 |
| 其余14个模型 | <25% | 超过75%任务破坏原有功能 |

### 2.3 目标

- **硬性门禁**：零退化率 = 100%（任何回归阻断合并）
- **趋势追踪**：监控零退化率随迭代次数的变化

---

## 三、回归检测流程

### 3.1 变更前基线

```bash
# 1. 记录基线测试结果
test_results_before = run_full_test_suite()
# 输出: { test_name: pass/fail, duration: ms }

# 2. 记录性能基线
perf_baseline = run_benchmarks()
# 输出: { benchmark_name: ops_per_sec, p99_latency: ms }
```

### 3.2 变更后验证

```bash
# 1. 运行相同测试套件
test_results_after = run_full_test_suite()

# 2. 比对差异
regressions = []
for test in test_results_before:
    if test.passed_before and not test.passed_after:
        regressions.append({
            test: test.name,
            type: "functional_regression",
            severity: "Critical"
        })

# 3. 性能比对
for bench in perf_baseline:
    if bench.ops_after < bench.ops_before * 0.9:  # 10% 退化阈值
        regressions.append({
            bench: bench.name,
            type: "performance_regression",
            severity: "Warning",
            degradation: (bench.ops_before - bench.ops_after) / bench.ops_before
        })
```

### 3.3 回归分类处理

| 回归类型 | 处理方式 | 是否阻断 |
|---------|---------|---------|
| 功能回归 | 必须修复 | ✅ 阻断合并 |
| 性能回归 >10% | 必须优化或说明 | ✅ 阻断合并 |
| 性能回归 5-10% | 需评估和说明 | ⚠️ 条件阻断 |
| 兼容性回归 | 需迁移文档 | ✅ 阻断合并 |
| 安全回归 | 立即修复 | ✅ 阻断合并 |

---

## 四、非对称评分体系


### 4.1 核心原则

**破坏现有功能的惩罚 > 增加新功能的奖励**

```
改进时（新增通过测试）:
  score = (new_pass - baseline_pass) / (target_pass - baseline_pass)
  范围: [0, 1]
  满分 = 1.0（完全达成目标）

退步时（原有测试失败）:
  score = (new_pass - baseline_pass) / baseline_pass
  范围: [-1, 0]
  最差 = -1.0（完全破坏所有功能）
```

### 4.2 非对称设计的深层逻辑

1. **破坏代价不对称**：破坏一个关键功能的代价远大于增加一个新功能的价值
2. **信任建立难、破坏易**：用户对系统的信任需要长期建立，但一次回归即可破坏
3. **回归的连锁效应**：一个回归可能触发下游依赖的连锁失败
4. **修复成本不对称**：引入回归后定位和修复的成本通常高于引入新功能

### 4.3 评分示例

```
基线: 100 个测试通过
目标: 120 个测试通过

场景 A（改进 +10，无回归）:
  新通过: 110
  score = (110 - 100) / (120 - 100) = 0.5  ✅ 正分

场景 B（改进 +10，但回归 -3）:
  新通过: 107 (110 新通过 - 3 回归)
  改进分 = (107 - 100) / (120 - 100) = 0.35
  回归扣分 = 3 / 100 = 0.03
  非对称总分 = 0.35 - 0.03 × 2 = 0.29  (回归惩罚翻倍)

场景 C（改进 +20，但回归 -15）:
  新通过: 105 (120 新通过 - 15 回归)
  改进分 = (105 - 100) / (120 - 100) = 0.25
  回归扣分 = 15 / 100 = 0.15
  非对称总分 = 0.25 - 0.15 × 2 = -0.05  ⚠️ 负分
```

---

## 五、CI 门禁配置

### 5.1 GitHub Actions 门禁示例

```yaml
# .github/workflows/quality-gate.yml
name: Quality Gate
on: [pull_request]

jobs:
  regression-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # 获取完整历史用于比对

      - name: Run baseline tests
        run: |
          git checkout origin/${{ github.base_ref }}
          go test ./... -v -json > baseline.json 2>&1 || true

      - name: Run current tests
        run: |
          git checkout ${{ github.sha }}
          go test ./... -v -json > current.json 2>&1

      - name: Check regressions
        run: |
          python scripts/check_regression.py baseline.json current.json
          # 退出码 0 = 无回归，1 = 有回归

  quality-metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check MI threshold
        run: |
          # 新增/修改文件的 MI 必须 ≥ 15
          CHANGED_FILES=$(git diff --name-only origin/${{ github.base_ref }} HEAD | grep '\.\(go\|ts\|rs\|cpp\|c\)$')
          for file in $CHANGED_FILES; do
            MI=$(python scripts/calculate_mi.py "$file")
            if [ $(echo "$MI < 15" | bc -l) -eq 1 ]; then
              echo "❌ $file MI=$MI (threshold: 15)"
              exit 1
            fi
          done

  health-score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Calculate health score
        run: |
          SCORE=$(python scripts/health_score.py --scope changed-files)
          echo "Health score: $SCORE"
          if [ $SCORE -lt 70 ]; then
            echo "❌ Health score $SCORE < 70 (threshold)"
            exit 1
          fi
```

### 5.2 门禁规则汇总

| 门禁 | 阈值 | 类型 | 失败行为 |
|------|------|------|---------|
| 零退化率 | = 100% | 硬性 | 阻断 PR |
| 健康分 | ≥ 70 | 软性 | 警告 + 需人工审批 |
| 发布健康分 | ≥ 80 | 硬性 | 阻断发布 |
| 新代码 MI | ≥ 15 | 硬性 | 阻断 PR |
| 圈复杂度 | ≤ 15 | 硬性 | 阻断 PR |
| 循环依赖 | = 0 | 硬性 | 阻断 PR |
| 性能退化 | < 10% | 软性 | 警告 + 需说明 |

---

## 六、回归追踪趋势

### 6.1 迭代级追踪

```
```

### 6.2 趋势分析

| 指标 | 健康趋势 | 危险趋势 |
|------|---------|---------|
| 零退化率 | 稳定 100% | 逐渐下降 |
| 回归幅度 | 递减 | 递增 |
| 修复时间 | 短 | 越来越长 |

### 6.3 预警机制

- 连续 2 次迭代出现回归 → 自动触发深度审查
- 零退化率低于 80% → 团队质量复盘会议
