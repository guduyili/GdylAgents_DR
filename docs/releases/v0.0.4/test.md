# v0.0.4：修复并发完成通知丢失

## 范围与方案

- 日期：2026-09-16；基线：`v0.0.3` / `279d1b9`。
- 根因：主循环统计一个完成通知后，批量清理会丢弃其他完成通知，导致完成计数不足而永久等待。
- 最小修复：移除正常消费分支中的批量清理，让主循环逐条统计所有通知；保留退出时的公开事件清理，不改变接口。
- 同步简化项目规则：Superpowers 仅作参考，默认用本文件合并范围、验证和结论，不再强制五份流程文档。全局用户准则另存于 `C:/Users/lzy33/.codex/AGENTS.md`，不属于项目 Git 内容。

## 测试与实际结果

Windows，Python 3.11.14，pytest 9.0.3，使用现有 `.venv-test`，不调用真实模型或搜索。

1. 新增两个固定事件顺序用例：3 个任务全部完成，以及其中一个失败。同步线程池替身先执行所有任务，再开始消费队列；若完成后仍读取空队列，立即报错，避免测试挂死。
2. 旧生产代码运行新增用例：**2 failed, 1 deselected**，均报 `All workers finished but completion notifications were lost`。
3. 修复后相关回归：**35 passed, 1 warning，2.42 秒**。覆盖两个新用例、真实线程池 10 个任务/并发上限 3、取消、quick 模式、公开事件顺序与元数据。
4. 新用例确认来源事件完整、有失败时传递原错误、最终报告和 done 各一次、内部通知不外泄。原真实并发用例新增 done 终态断言。

依赖警告来自 HelloAgents/Pydantic 的弃用配置。本次回归使用父进程 30 秒截止，实际正常结束，未触发终止。

## 复现

从仓库根目录进入 `backend`：

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_stream_runner_concurrency.py tests/test_stream_runner.py tests/test_stream_observability.py tests/test_stream_observability_round2.py tests/test_observability_fields.py tests/test_quick_mode.py tests/test_stream_runner_cancellation.py tests/test_stream_events.py -q --tb=short
```

在旧版本重做红阶段时，只应用本版测试变更，然后运行 `tests/test_stream_runner_concurrency.py -k counts_all_queued`，不会启动可能挂起的旧真实并发用例。需要为整组测试加外部截止时，可沿用 [v0.0.3 的父进程限时方法](../v0.0.3/test.md)，替换测试文件列表并将截止改为 30 秒。

## 结论与后续

本版修复的完成计数问题已由确定性测试和真实并发回归验证。此次未重复全量测试；[上一版记录](../v0.0.3/test.md)中的存储配置假设冲突尚未修复，不宣称全量通过。下一版处理该测试的配置隔离，再继续线程超时边界实验。

本地分支 `codex/v0.0.4-worker-completion`，标签 `v0.0.4`；不发布包、不推送，保留原有未跟踪的 `data/`。
