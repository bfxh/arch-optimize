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

### 2.2 外部参考基准（非本仓实测，勿当阈值用）

下表来自外部评测，本仓脚本无法复算，文档也未记录来源与日期。引用前自行核实，不要用其中的数字给项目定级。

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

### 4.2 当前实现与本节公式的差异（未修，读数字前必看）

`regression_guard.py compare` 并没有按上面的两段分支计算，它算的是：

```
target_pass = baseline_pass + max(1, len(new_tests))
非对称总分   = (new_pass - baseline_pass) / (target_pass - baseline_pass)
             - 2 × regression_count / baseline_pass
```

由此产生三个后果：

1. 没有新增测试时 `target_pass - baseline_pass == 1`，改进分不受 [0,1] 约束。实测「3 个原有失败测试转绿 + 1 个真回归」得 **+1.979**——惩罚方向与"破坏 > 新增"相反。
2. 4.3 的示例假设 target=120 可外部指定，但 `record` 不写 target 字段，CLI 也没有对应参数，该示例当前无法用脚本复现。
3. 真正拦合并的是硬门 `regression_count == 0`（退出码 1），与这个分数无关。引用结论请引用 `regressions` 列表和退出码，不要引用 `non_asymmetric_score`。

### 4.3 非对称设计的深层逻辑

1. **破坏代价不对称**：破坏一个关键功能的代价远大于增加一个新功能的价值
2. **信任建立难、破坏易**：用户对系统的信任需要长期建立，但一次回归即可破坏
3. **回归的连锁效应**：一个回归可能触发下游依赖的连锁失败
4. **修复成本不对称**：引入回归后定位和修复的成本通常高于引入新功能

### 4.4 评分示例

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

以下命令只用本仓实际存在的脚本与参数（三条 `run` 都已本地跑通，退出码按预期）。注意第二步：`compare` 只看同名测试 pass→fail，**测试被删或改名不会判红**，所以"测试集不缩减"必须单独设一道。

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
          fetch-depth: 0  # 需要 base ref 才能记录基线

      - name: Record baseline tests (on base ref)
        env:
          # 事件字段走 env 传入，不直接插值进 shell
          BASE_REF: ${{ github.base_ref }}
        run: |
          git checkout "origin/$BASE_REF"
          python scripts/regression_guard.py record --output baseline.json \
            --test-cmd "python -m pytest -v"

      - name: Record current tests
        run: |
          git checkout ${{ github.sha }}
          python scripts/regression_guard.py record --output current.json \
            --test-cmd "python -m pytest -v"

      - name: Check regressions (hard gate)
        run: |
          # 有 pass->fail 回归时退出码为 1
          python scripts/regression_guard.py compare \
            --baseline baseline.json --current current.json --json

      - name: Test set must not shrink (compare 不判这一步)
        run: |
          python - <<'PY'
          import json, sys
          b = json.load(open("baseline.json", encoding="utf-8"))
          c = json.load(open("current.json", encoding="utf-8"))
          gone = sorted(set(b["results"]) - set(c["results"]))
          if gone or len(c["results"]) < len(b["results"]):
              print("测试被删除或改名: %d 个" % len(gone), gone[:10])
              sys.exit(1)
          PY

  quality-metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Changed files must keep MI >= 15
        env:
          BASE: origin/${{ github.base_ref }}
        run: |
          python - <<'PY'
          import json, os, subprocess, sys
          EXTS = {".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs",
                  ".c", ".cpp", ".cc", ".h", ".hpp"}
          listed = subprocess.run(["git", "diff", "--name-only", os.environ["BASE"], "HEAD"],
                                  capture_output=True, text=True).stdout.split()
          bad = []
          for f in listed:
              if os.path.splitext(f)[1].lower() not in EXTS or not os.path.exists(f):
                  continue
              out = subprocess.run([sys.executable, "scripts/quality_metrics.py",
                                    "--file", f, "--json"],
                                   capture_output=True, text=True, encoding="utf-8")
              data = json.loads(out.stdout)
              if not data.get("files"):
                  continue
              mi = data["files"][0]["maintainability_index"]
              print("%s MI=%s" % (f, mi))
              if mi < 15:
                  bad.append(f)
          if bad:
              print("MI < 15:", bad)
              sys.exit(1)
          PY

  health-score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Health score >= 70
        run: |
          # 注意：健康分无规模归一，只对同一 scope 的前后两次扫描可比
          python scripts/risk_diagnose.py --target src --json \
            | python -c 'import json,sys; s=json.load(sys.stdin)["health_score"]["score"]; print("health:", s); sys.exit(0 if s >= 70 else 1)'
```

### 5.2 门禁规则汇总

| 门禁 | 阈值 | 类型 | 失败行为 | 本仓脚本能否直接判 |
|------|------|------|---------|--------------------|
| 零退化率 | = 100% | 硬性 | 阻断 PR | `compare` 退出码 1；需另加"测试集不缩减"一道（见 5.1） |
| 健康分 | ≥ 70 | 软性 | 警告 + 需人工审批 | 只给分数，判断要自己写（见 5.1）；无规模归一 |
| 发布健康分 | ≥ 80 | 硬性 | 阻断发布 | **无实现** |
| 新代码 MI | ≥ 15 | 硬性 | 阻断 PR | 需逐文件 `--file`（脚本无"新增代码"概念） |
| 圈复杂度 | ≤ 15 | 硬性 | 阻断 PR | Python 可判；非 Python 因 CC 正则少计布尔运算符而几乎不触发 |
| 循环依赖 | = 0 | 硬性 | 阻断 PR | 部分：相对导入与包内环检不出，0 条 ≠ 无环 |
| 性能退化 | < 10% | 软性 | 警告 + 需说明 | 仅 go test -json / jest 有 duration；pytest、cargo 解析器恒为 0 → 该档不生效 |

---

## 六、回归追踪趋势

### 6.1 迭代级追踪

`regression_guard.py` 不写历史文件，下面的数组要自己追加（`compare --json` 的字段 → 历史字段映射见表）。这个数组就是 `evoscore --history` 的输入格式。

```json
[
  { "iteration": 1, "passed": 100, "target": 120, "regressions": 0 },
  { "iteration": 2, "passed": 107, "target": 120, "regressions": 3 }
]
```

| evoscore 需要的字段 | 从哪来 |
|---------------------|--------|
| `passed` | `compare` 输出的 `current.passed`（或 `record` 输出的 `passed`） |
| `regressions` | `len(compare.regressions)` |
| `iteration` | 自己递增 |
| `target` | 自己设定；`record`/`compare` 都不产出 target，evoscore 缺失时回退为 `baseline_passed + 1` |

### 6.2 趋势分析

| 指标 | 健康趋势 | 危险趋势 |
|------|---------|---------|
| 零退化率 | 稳定 100% | 逐渐下降 |
| 回归幅度 | 递减 | 递增 |
| 修复时间 | 短 | 越来越长 |

### 6.3 预警机制

- 连续 2 次迭代出现回归 → 自动触发深度审查
- 零退化率低于 80% → 团队质量复盘会议
