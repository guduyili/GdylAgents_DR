# v0.0.9：向搜索适配器传递剩余预算

## 范围与方案

- 日期：2026-09-16；基线：`v0.0.8` / `912c0a8`。
- 问题：跨后端回退虽检查预算，但 DuckDuckGo 仍从配置取得完整超时；创建适配器的耗时也未计入调用前检查。
- 增加可选 `BudgetedSearchBackend` 协议：支持者通过 `search_with_budget` 接收浮点剩余秒数；原 `search` 接口及旧适配器继续兼容。
- DuckDuckGo 实现该能力，原直接调用仍使用配置预算。回退链创建适配器后重新计算剩余预算，耗尽时不发起搜索。
- 不修改共享 Configuration，不绕过整型超时字段校验。SDK 超时仍受内部单次 15 秒上限约束。

## 验证

Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`。使用真实回退调度与 DuckDuckGo 适配器、可控时钟及假 DDGS，无网络或睡眠。

新增 4 个场景：总预算 2 秒，主后端失败消耗 0.75 秒；备用适配器创建分别消耗 0.25、1、1.25、2 秒。前两项验证 SDK 收到 1、0.25 秒；后两项验证未启动 SDK。共同验证结果、错误/预算提示及配置不变。既有测试覆盖旧接口适配器兼容、DuckDuckGo 内部重试共享预算和直接调用。

- 修复前 `test_search_fallback.py`：**4 failed, 6 passed, 1 warning，1.87 秒**。四个新增场景均错误地给 SDK 传入 2 秒。
- 修复后两个搜索测试模块：**17 passed, 1 warning，1.32 秒**。
- 后端 `tests` 全量：**139 passed, 21 warnings，6.38 秒**。父进程 45 秒超时未触发，无中止。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_fallback.py tests/test_search_backends.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

修复前复现：独立工作区检出 `v0.0.8`，仅应用本版测试改动，运行 `test_search_fallback.py`。全量限时方式沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标为 `tests`、上限 45 秒。

## 边界与后续

目前仅 DuckDuckGo 支持预算能力；经 HelloAgents SearchTool 的适配器沿用旧接口。浮点预算传递并非严格端到端硬截止：调度开销、SDK 实际超时行为及已启动线程仍不受强制终止保证。未验证真实联网、模型或前端。

下一版优先把取消信号接入搜索重试边界，避免取消后继续启动后续尝试；线程资源释放另行评估。

分支 `codex/v0.0.9-adapter-budget`，本地 annotated tag `v0.0.9`；未推送、未发布包，原有 `data/` 保留且不提交。
