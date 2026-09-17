# v0.0.3 实施计划

1. 建立 `codex/v0.0.3-test-executor-contract` 分支；独立提交项目规则。
2. 对照 `TaskExecutor.execute()` 与 `StreamRunner` 调用，确认 6 个替身属于同一根因。
3. 在 `test_stream_observability.py` 和 `test_stream_observability_round2.py` 补 3 条工具事件断言；运行原有用例复现失败。
4. 对 `test_observability_fields.py`、`test_quick_mode.py`、`test_stream_observability.py`、`test_stream_observability_round2.py`、`test_stream_runner.py`、`test_stream_runner_concurrency.py` 中的执行器替身增加显式参数与 Event 导入。
5. 运行相关回归，并对并发用例设置进程级时间上限。用全量 `-x` 探测下一阻塞，不无界等待。
6. 完成 `test.md`、审查与总结，更新版本索引，提交并创建本地 `v0.0.3` 标签。

详细复现命令、结果与限制最终记录在同目录 `test.md`。
