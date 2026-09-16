# v0.0.3 版本总结

- 项目级协作规则写入 `AGENTS.md`，单独提交 `976942d`。
- 6 个流式执行器测试替身对齐 `stop_event`；3 项事件测试增加真实产出断言。
- 修复前 8 failed / 2 passed；修复后相关回归 40 passed。
- 并发用例仍超时；全量补齐本地 Redis 依赖后为 59 passed / 1 failed（首失败停止）。
- 下一版优先修复完成通知丢失导致的并发停顿，再处理测试配置隔离。
- 本地分支 `codex/v0.0.3-test-executor-contract`，迭代标签 `v0.0.3`；不调整包版本、不推送、不合并主分支。

详情：[test.md](test.md)、[版本索引](../README.md)。
