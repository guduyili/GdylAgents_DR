# v0.4.0：证据支持、时效与摘要检查

## 版本范围

- 日期：2026-09-18；基线：`v0.3.0` / `28d0f39`。
- 扩展固定材料评估器，不改变生产搜索决策流程；决策循环的 Evidence 结构保留 `published_at`，使评估可以使用来源日期。
- `ModeMetrics` 新增 `evidence_support`、`freshness_coverage` 和 `summary_correctness`。
- 证据支持：对每个标注主张，要求声明的来源 URL 全部存在，并且来源标题/正文包含全部 `required_terms`。
- 时效覆盖：对声明 `max_age_days` 的主张，按案例 `as_of` 日期检查所有要求来源的 `published_at`；缺失、格式错误或超期均不计入。
- 摘要检查：按案例 `summary_required_terms` 检查 fixed/decision 的标注摘要文本，作为摘要正确性的确定性代理指标。
- 保留已有 URL 覆盖、冲突组、搜索次数、停止原因、错误数和来源增益；新增 `claim_coverage_gain` 之外，CLI 输出三个质量指标及其差值所需的基础数据。

## 用例与实际结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；固定材料和确定性动作，无网络或模型调用。

新增 3 项断言：冲突案例验证正文关键词支持、30 天时效和摘要关键词均为 1；资料不足保持 0 覆盖；陈旧来源和无关正文即使 URL 存在，也不会计为证据支持或时效覆盖。原有安全停止与 URL 覆盖断言继续保留。

- 修改前新增测试：**2 failed, 5 passed，约 2.4 秒**；质量指标尚不存在。
- 初次实现发现决策循环 Evidence 丢失 `published_at`，导致时效指标为 0；随后保留该字段并回归，未绕过断言。
- 修复后评估模块：**7 passed，1 warning**。
- 内置 CLI：**5/5 passed**；冲突案例 decision 的 claim coverage/evidence support/freshness/summary 均为 1，资料不足案例均为 0。
- 后端全量 `tests`：**203 passed，21 warnings，6.67 秒**；父进程 45 秒上限未触发，无中止。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_action_eval.py tests/test_decision_loop.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m evals.action_eval --cases evals/action_cases.jsonl
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

本版无前端改动，不重复运行前端构建；前端 v0.1.0 回归结果仍记录在对应版本文档。

## 边界与下一步

这些指标是固定材料上的标注代理：正文关键词出现不等于主张被语义支持，日期字段也不代表来源可信度。摘要检查只检查标注词是否出现，不判断表述是否准确、是否遗漏反例或是否正确处理冲突。案例标注错误会直接影响分数，不能据此宣称真实模型准确率或统计显著性。

下一版可加入人工标注的来源片段、主张极性和矛盾结论标签，单独评估检索覆盖、证据支持、时效和摘要正确性；真实模型评估应记录模型版本、提示词、材料快照及失败样本。

分支 `codex/v0.4.0-evidence-quality`，本地 annotated tag `v0.4.0`；后续将推送该分支和标签。原有未跟踪 `data/` 保留且不提交。
