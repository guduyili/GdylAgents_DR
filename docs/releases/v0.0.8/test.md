# v0.0.8：预算耗尽后停止跨后端回退

## 范围与方案

- 日期：2026-09-16；基线：`v0.0.7` / `d425fb9`。
- 问题：某搜索后端失败时，即使已耗尽本次搜索预算，仍创建并调用后续后端。
- 修复：`FallbackSearchBackend.search()` 入口建立单调时钟截止时间；每轮创建后端前检查预算，耗尽即结束并返回已有错误及预算提示。截止时间不因切换后端重置，不修改调用者配置。
- 保留预算内的回退、结果格式及错误信息；日志改为“未获得结果”，避免未尝试的后端被描述成失败。

## 验证

Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；使用假搜索后端和可控时钟，无真实网络或睡眠。

新增 4 个场景：恰好耗尽预算、超过预算、预算内回退成功、两个失败后端累计耗尽预算。断言后续后端未创建/调用、错误与预算提示保留、正常结果仍返回、原配置不变。

- 旧实现：**3 failed, 1 passed, 2 deselected**；耗尽后仍调用第二或第三个后端。
- 修复后完整 `backend/tests`：**135 passed, 21 warnings，7.25 秒**。父进程 45 秒截止未触发。
- 警告为已有 Pydantic/FastAPI 弃用提示。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_fallback.py -k budget_exhaustion -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

旧行为可在独立工作区检出 `v0.0.7`，仅应用新增测试后复现。全量限时方式沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标为 `tests`、上限 45 秒。

## 边界与后续

本版保证每轮后端创建前检查同一个截止时间。已启动的后端仍可能超时返回；剩余预算未传给各 SDK，后端创建耗时也未再次扣减检查。未强制停止线程、未把用户取消信号传入搜索链，也未做公网耗时保证。

下一版将剩余预算传入支持该能力的具体适配器，避免它拿到整份原始预算；不通过修改共享配置或绕过配置校验实现。全量通过仅指后端 `tests`。

分支 `codex/v0.0.8-fallback-deadline`，本地标签 `v0.0.8`；未推送、未发布包，原有 `data/` 保留且不提交。
