# v0.0.11：DuckDuckGo 内部重试感知取消

## 范围与方案

- 日期：2026-09-16；基线：`v0.0.10` / `4bd3491`。
- 问题：跨后端回退已检查取消，但 DuckDuckGo 的 lite/api/html 尝试未收到信号；内部通用异常捕获还会吞掉 `ResearchCancelled`。
- DuckDuckGo 实现取消能力，将信号传入 `_ddgs_search`，在入口、每轮创建客户端前、进入客户端后、请求返回后及失败处理时检查取消。取消异常单独重新抛出。
- 取消能力接口增加可选 `timeout_seconds`，同时传递剩余预算和取消信号，避免能力选择导致预算重置。DuckDuckGo 与 FallbackSearchBackend 均实现该参数，原 search/search_with_budget 调用保留。
- 既有规范化测试替身仅增加 stop_event 参数以匹配真实 helper，原断言保留。

## 测试与实际结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`。假 DDGS、可控时钟，无网络和睡眠。

新增 9 项用例：通过真实回退链覆盖预取消、进入客户端时取消、失败/空结果/成功返回时取消、SDK 直接抛取消异常、退出客户端时取消；直接调用 DuckDuckGo 再覆盖预取消和成功返回时取消。

验证内部最多尝试 lite，取消后不再启动 api/html 或其他搜索后端；进入客户端后取消不调用 text；取消异常原对象透传；已进入的上下文执行退出。总预算 2 秒、创建适配器耗时 1.75 秒时，客户端仍收到 0.25 秒。

- 修复前取消测试模块：**6 failed, 12 passed, 1 warning，2.09 秒**（新增用例中 6 失败、3 通过）。可见取消后调用全部三种内部后端，取消异常被吞掉，直接取消入口不存在。
- 修复后搜索相关三个模块：**35 passed, 1 warning，1.44 秒**。
- 后端 `tests` 全量：**157 passed, 21 warnings，6.59 秒**。父进程 45 秒截止未触发，无中止。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_cancellation.py tests/test_search_backends.py tests/test_search_fallback.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

修复前复现：独立工作区检出 `v0.0.10`，仅应用 `test_search_cancellation.py` 的新增测试并运行该文件。全量限时方式沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标 `tests`、上限 45 秒。

## 边界与后续

这是协作取消，不终止运行中的 SDK 请求或线程，也无法原子阻止检查后才发生的取消。假客户端的退出断言只证明上下文退出路径，不证明真实 SDK 资源全部释放。未验证网络、模型质量或前端。

仅实现旧 search 或 search_with_budget 的适配器仍可用；实现取消能力的扩展适配器应接受新增的可选 timeout_seconds 参数。当前仓库内两个实现均已更新。

下一版优先将搜索超时转换为本次调用的停止信号，避免调用方超时返回后后台继续重试；不得因此设置整次研究的共享取消事件。

分支 `codex/v0.0.11-duckduckgo-cancellation`，本地 annotated tag `v0.0.11`；未推送或发布包。原有未跟踪 `data/` 保留且不提交。
