# v0.0.12：搜索超时停止本次调用的后台重试

## 范围与方案

- 日期：2026-09-17；基线：`v0.0.11` / `660a72b`。
- 问题：调用方超时返回时未通知后台搜索，阻塞请求稍后失败仍可能触发 DuckDuckGo 的 api/html 重试。
- 增加 ScopedStopSignal，将父级取消信号与独立本地 Event 组合。只读父信号，set 仅设置本地事件。
- TaskExecutor 每次搜索创建独立信号，传给支持取消的后端或默认 dispatcher；搜索等待结束时在 finally 设置本地信号。正常完成后该信号也结束，不复用到下一次调用。
- 外层等待仍观察原用户信号，所以超时仍抛 TimeoutError，任务保持 failed；用户取消仍对应 cancelled。总结路径不改动。

## 测试与实际结果

Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；假 SDK、真实线程池和有界 Event 同步，无联网。

新增 4 项场景为注入后端/默认 dispatcher × 有/无共享取消事件。用可控调用方时钟触发超时，同时保持搜索链预算可用，以单独验证本次停止信号的作用。先确认调用方返回且 SDK 尚未退出，再释放请求并使其失败，断言只有 lite 调用、工作线程收到 ResearchCancelled、父事件未设置。随后复用同一执行器进行第二次搜索，验证信号隔离与正常结果。

所有阻塞等待设 2～3 秒上限，finally 释放请求并等待搜索链退出；全量另设父进程 45 秒上限。既有用例继续验证 failed/cancelled 终态、用户取消传递及旧接口兼容。

- 修复前新增文件：**4 failed, 1 warning，7.52 秒**，均观察到超时后的 api 重试。
- 修复后相关四个模块：**27 passed, 1 warning，5.34 秒**。
- 后端 `tests` 全量：**161 passed, 21 warnings，8.45 秒**；45 秒上限未触发，无中止。
- 警告为既有 Pydantic/FastAPI 弃用提示；`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_timeout_stop.py tests/test_search_cancellation.py tests/test_task_executor_reliability.py tests/test_task_executor_cancellation.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

修复前复现：独立工作区检出 `v0.0.11`，仅应用新增测试文件并运行。全量限时方式沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标 `tests`、上限 45 秒。

## 边界与后续

本版阻止支持停止信号的搜索链在检查边界继续工作，不能中断已运行的 SDK、原子阻止检查后的竞态调用，或控制自定义旧接口内部重试。底层请求永久阻塞时，线程仍可能占用资源；真实网络耗时、SDK 资源回收、前端与模型质量未验证。

搜索可靠性的当前小闭环已具备测试基线、预算传递、取消和超时停止。后续可沿学习主线 A 开始单任务 search/finish 动作契约实验，先验证动作和参数约束，再逐步接入决策循环；线程资源上限问题继续保留为独立可靠性议题。

分支 `codex/v0.0.12-search-timeout-stop`，本地 annotated tag `v0.0.12`；未推送或发布包。原有未跟踪 `data/` 保留且不提交。
