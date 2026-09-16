# v0.0.2 实施计划

1. 将已完成路线图独立提交，建立 `codex/v0.0.2-fact-check-baseline` 分支。
2. 在 `backend/tests/test_fact_check_service.py` 添加固定材料正反例，验证大小写、缺词阈值和中文术语；在 `backend/tests/test_task_executor_fact_check.py` 检查结果事件。
3. 运行新增用例，记录旧实现失败断言。
4. 在 `backend/src/services/fact_check_service.py` 将匹配条件改为 `term.lower() in lowered_sources`，其余规则保留。
5. 运行相关回归；根据结果核对影响范围与审查意见。
6. 完成同目录 `test.md`、`review.md`、`final_report.md`，更新版本索引，提交并创建 `v0.0.2` Git 标签。

验证命令从仓库根目录进入 `backend`，使用现有 Windows 测试环境。pytest 的 `pythonpath` 相对配置根目录解析：

```powershell
cd backend
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_fact_check_service.py tests/test_task_executor_fact_check.py tests/test_stream_events.py -q
```
