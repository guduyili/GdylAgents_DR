# v0.2.0：动作级离线评估与 fixed/decision 对照

## 版本范围

- 日期：2026-09-17；基线：`v0.1.0` / `e3dca17`。
- 新增 `backend/evals/action_eval.py` 和 `action_cases.jsonl`，在固定材料上对照 fixed 单次搜索与 decision 决策循环。
- 每个案例可声明初始查询、查询到材料的映射、确定性动作序列、期望停止原因和最低来源数。评估器不访问网络、不调用模型，避免把外部波动当成算法改进。
- 输出统一指标：搜索次数、唯一 HTTP/HTTPS 来源数、停止原因、错误数、来源增益和通过状态。材料按 URL 去重，非法协议不会计入。
- 提供 CLI：`python -m evals.action_eval --cases evals/action_cases.jsonl`，每行输出一个 JSON 结果，适合后续保存和比较。

内置三个案例：空结果后改写查询、重复查询安全停止、非法动作安全停止。第一个案例展示 decision 在同一材料集上多搜索一次换取来源，后两个案例验证循环不会执行越界工具。

## 测试与实际结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`。评估用例只使用内存材料和确定性动作。

- 实现前新增评估测试：**1 collection error，0.31 秒**；`evals.action_eval` 尚不存在。
- 修复后动作评估测试：**4 passed，1 warning，1.45 秒**。
- CLI 运行内置 3 案例：**3/3 passed**；输出显示 `empty-then-rewrite` 的 fixed/decision 来源数为 0/1、搜索次数为 1/2，重复与非法动作分别在 1 次和 0 次搜索后停止。
- 后端全量回归：**200 passed，21 warnings，约 7 秒**；父进程 45 秒上限未触发，无中止。
- 前端代码未在本版修改；v0.1.0 已验证 Vitest 8 项和生产构建，本版只增加后端离线评估器。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_action_eval.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m evals.action_eval --cases evals/action_cases.jsonl
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

评估器输出是离线回归证据，不是联网研究质量分数；运行前不会读取密钥，也不会写运行数据库。

## 边界与下一步

当前评估动作序列由案例预先给定，尚未衡量真实模型决策质量；材料规模为学习和回归用途，不能推断统计显著性。指标只统计搜索和来源，不判断摘要事实是否正确，也不替代事实核对、报告评审或人工标注。

下一阶段可扩充固定案例的冲突来源、时效变化和资料不足类别，增加人工标注的主张覆盖指标，再接入真实模型的抽样评估。评估失败应先定位动作契约、搜索证据或总结质量属于哪一层，避免用单一总分掩盖问题。

分支 `codex/v0.2.0-action-evaluation`，本地 annotated tag `v0.2.0`；未推送或发布包。原有未跟踪 `data/` 保留且不提交。
