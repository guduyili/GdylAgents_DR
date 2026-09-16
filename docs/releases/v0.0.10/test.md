# v0.0.10：取消后停止跨后端回退

## 范围与方案

- 日期：2026-09-16；基线：`v0.0.9` / `2f12fa1`。
- 问题：TaskExecutor 的等待线程感知取消，但搜索工作线程未收到信号；主后端失败后仍可能启动备用后端。`ResearchCancelled` 也被通用异常处理误当作搜索失败。
- 引入可选 `CancellableSearchBackend` 能力，保持原 `search` 接口。TaskExecutor 将信号传给支持者；默认 dispatch_search 路径也传递信号。自定义旧接口保持兼容，执行前后检查取消。
- FallbackSearchBackend 在后端创建前后、调用返回后和普通异常处理时检查取消；单独重新抛出 `ResearchCancelled`，不触发降级。原预算透传与检查保留。
- 本版只覆盖跨后端边界，维持单一最小改进。

## 用例与结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；无联网或真实模型调用。

新增 9 项测试：注入搜索后端和默认调度两条路径，各覆盖创建期间取消、失败时取消、成功返回时取消、后端直接抛出取消异常；另覆盖进入搜索链前已取消。验证备用后端不创建、创建期间取消不调用搜索、任务状态和事件为 cancelled、研究结果与来源未写入。

新增集成用例同步执行搜索函数，避免外层等待循环提前返回掩盖搜索链仍继续运行的问题；不将它们作为线程调度或终止测试。全量回归同时运行既有真实线程取消、超时及旧适配器兼容用例。

- 修复前新增用例：**9 failed, 1 warning，2.13 秒**。出现继续调用备用后端、取消后标记 skipped 等行为；预取消能力入口尚不存在。
- 修复后相关四个模块：**28 passed, 1 warning，1.60 秒**。
- 后端 `tests` 全量：**148 passed, 21 warnings，6.71 秒**；父进程 45 秒截止未触发，无中止。
- 21 条警告为既有 Pydantic/FastAPI 弃用提示。`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_cancellation.py tests/test_search_backends.py tests/test_search_fallback.py tests/test_task_executor.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

修复前复现：独立工作区检出 `v0.0.9`，仅应用新增 `test_search_cancellation.py` 并运行该文件。全量限时沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标 `tests`、上限 45 秒。

## 边界与后续

取消是边界处的协作检查，不能原子阻止检查后瞬间开始的调用，也不能终止已经运行的 SDK 或线程。DuckDuckGo 内部 lite/api/html 重试尚未接收取消信号；自定义旧适配器及 dispatcher 的内部循环同样不受控制。取消发生在搜索阶段之后的浏览器抓取、非流式总结等路径不在本版范围。

下一版将取消信号传入 DuckDuckGo 内部重试边界，并验证取消异常不会被内部通用异常捕获。未验证真实网络耗时、模型质量或前端。

分支 `codex/v0.0.10-search-cancellation`；本地 annotated tag `v0.0.10`。未推送、未发布包；原有未跟踪 `data/` 保留且不提交。
