# v0.0.5：运行存储 API 测试配置隔离

## 范围

- 日期：2026-09-16；基线：`v0.0.4` / `4170316`。
- 问题：测试假定应用使用内存存储，却继承开发环境的 SQLite 设置；取消测试同样未显式选择存储和取消广播后端。
- 方案：新增按需启用的 `isolated_run_configuration` fixture，仅供运行查询和取消 API 两个测试模块使用。显式设置内存存储、临时数据库路径和内存取消注册表，测试结束由 monkeypatch 还原环境。
- SQLite 用例仍显式切换 SQLite、使用 `tmp_path` 并重开数据库验证持久化；取消用例新增类型断言。生产代码、默认配置与依赖均未修改。

## 实际验证

Windows，Python 3.11.14，pytest 9.0.3，现有 `backend/.venv-test`；不调用真实 LLM 或搜索。

| 阶段 | 结果 |
|---|---|
| 修复前两个 API 测试模块 | **1 failed, 3 passed**：期望内存存储，实际为 SQLite |
| 修复后 API + 配置 + 两种存储回归 | **14 passed**，2.27 秒 |
| 后端完整 `backend/tests` | **125 passed**，8.61 秒；45 秒进程截止未触发 |

21 条警告来自已有的 Pydantic 和 FastAPI 弃用接口，未作为本版改动。`--disable-warnings` 仅收起警告详情，不改变结果。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
# 相关回归
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_research_runs_api.py tests/test_research_runs_cancel_api.py tests/test_config.py tests/test_sqlite_research_run_store.py tests/test_research_run_store.py -q --tb=short --disable-warnings
# 全量后端测试
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

实际全量运行使用与 [v0.0.3](../v0.0.3/test.md) 相同的父进程截止方式，目标替换为 `tests`，时间上限设为 45 秒。

## 边界与下一步

全量通过仅指 `backend/tests`，不包含 `backend/src` 中的手工实验脚本、前端构建或联网研究质量评估。fixture 隔离的是用例执行期间创建的应用；`main` 模块在导入时创建全局 app 的副作用未在本版重构。

测试基线已恢复；下一版按主线研究线程超时与真实返回时间的边界，先写可控阻塞反例。版本分支 `codex/v0.0.5-test-store-isolation`，本地标签 `v0.0.5`；原有 `data/` 保留且不提交。
