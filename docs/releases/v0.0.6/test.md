# v0.0.6：超时与取消及时返回

## 范围与修复

- 日期：2026-09-16；基线：`v0.0.5` / `5ec8f3b`。
- 问题：`_call_with_timeout()` 使用线程池上下文管理器；即使已检测到超时或取消，退出时仍等待运行中的调用，延迟失败/取消事件。
- 修复：显式管理线程池，在 `finally` 中 `shutdown(wait=False, cancel_futures=True)`。调用方停止等待，未开始的工作取消；已运行的调用自行结束。正常结果和事件结构不变。
- 该 helper 同时用于搜索和非流式总结；流式总结已有独立实现，本轮不改。

## 验证

Windows，Python 3.11.14，pytest 9.0.3，使用现有 `backend/.venv-test`，无真实模型或网络搜索。

新增 2 个事件控制用例：底层搜索启动后等待释放信号，分别触发 1 秒超时和显式取消。要求调用方在 2.5 秒内返回、底层此时仍未结束；检查唯一失败/取消事件。最后释放底层调用并等待清理，验证迟到搜索结果不会再生成来源事件或改变任务终态。

| 阶段 | 实际结果 |
|---|---|
| 新用例 + 旧实现 | **2 failed, 2 deselected**；调用方仍等待阻塞搜索 |
| 修复后完整 `backend/tests` | **127 passed, 21 warnings，7.15 秒** |

全量运行使用父进程 45 秒截止，未触发终止。警告为既有 Pydantic/FastAPI 弃用提示。已有正常搜索、总结、失败和取消用例均包含在全量回归中。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
# 阻塞返回边界，测试自行释放阻塞并清理线程
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_task_executor_reliability.py -k returns_before -q --tb=short --disable-warnings
# 全量后端测试
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

若需验证旧行为，在独立工作区检出 `v0.0.5`，只应用本版测试文件变更后执行第一条测试命令。

## 限制与后续

- 此修复不强制终止线程、网络请求或外部副作用；底层无限阻塞仍可能占用资源、阻止进程正常退出，重复超时可能积压线程。
- 新测试只证明搜索返回值不会在超时后被本任务消费，不能证明任意工具不会自行修改共享状态或写入笔记；非流式总结等工具的迟到副作用仍需单独治理。
- 后续优先做底层搜索请求超时与资源回收约束，避免将“调用方返回”误当作“底层已停止”。
- 全量仅指 `backend/tests`，未执行前端构建或联网研究质量评估。

分支 `codex/v0.0.6-timeout-return`，本地标签 `v0.0.6`；无包发布或远程推送，原有 `data/` 保留。
