# v0.3.0：主张覆盖与冲突来源评估

## 版本范围

- 日期：2026-09-18；基线：`v0.2.0` / `a2175a1`。
- 扩展 `backend/evals/action_eval.py` 的固定材料评估，不改变生产搜索或决策循环路径。
- `ModeMetrics` 新增 `claim_coverage` 和 `conflict_groups`；案例可声明主张需要的来源 URL（`claims[].required_urls`）及冲突来源组（`conflict_groups`）。
- 主张覆盖按声明的必需 URL 是否全部出现在该模式收集到的合法 HTTP/HTTPS 来源中计算；冲突组在同一结果中同时出现至少两个来源时计数。结果仍按 URL 去重，非法协议不计入。
- `ActionEvalResult` 增加 `claim_coverage_gain`，保留原有搜索次数、来源数、停止原因、错误数和来源增益指标。CLI 输出 JSON，便于后续保存比较。
- 内置案例从 3 个扩展到 5 个：空结果改写、重复查询停止、非法动作停止、冲突来源主张覆盖、资料不足安全结束。

## 用例与实际结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；固定材料和确定性动作，无网络或模型调用。

新增 2 项断言：冲突案例验证 fixed/decision 主张覆盖为 0/1、冲突组为 1、来源增益为 1；资料不足案例验证 `no_evidence`、覆盖为 0、不会用空结果虚增质量。原 4 项评估测试继续保留。

- 修改前新增断言：**2 failed, 4 passed，8.86 秒**；评估指标尚无 `claim_coverage` 字段。
- 修复后评估模块：**6 passed，1 warning，1.42 秒**。
- 内置 CLI：**5/5 passed**。冲突案例 fixed/decision 的主张覆盖为 0/1，资料不足案例均为 0 并以 `no_evidence` 停止。
- 后端全量 `tests`：**202 passed，21 warnings，9.15 秒**；父进程 45 秒上限未触发，无中止。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_action_eval.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m evals.action_eval --cases evals/action_cases.jsonl
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

本版不需要前端构建；生产前端行为未修改。

## 边界与下一步

主张覆盖是来源 URL 的确定性代理指标，不阅读或判断来源正文是否真正支持主张，也不处理来源时效、可信度、矛盾结论的裁决。`required_urls` 来自案例标注，案例质量决定评估质量；不能据此宣称真实模型准确率或统计显著性。资料不足只验证安全停止，不代表系统能自动识别所有缺证据情况。

下一版可加入人工标注的主张与来源片段、时效字段和矛盾结论标签，分开报告检索覆盖、证据支持与总结正确性；真实模型评估应在固定材料上抽样并记录模型、提示词和失败样本。

分支 `codex/v0.3.0-evidence-coverage`，本地 annotated tag `v0.3.0`；后续将推送该分支和标签。原有未跟踪 `data/` 保留且不提交。
