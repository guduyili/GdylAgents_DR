# v0.0.3 Test：流式执行器测试契约

## 基线与环境

- 日期：2026-09-16。
- 业务基线：`v0.0.2` / `615b8e9`；规则提交：`976942d`。
- Windows，Python 3.11.14，pytest 9.0.3，解释器 `backend/.venv-test/Scripts/python.exe`。
- 本版只修改测试替身和测试断言，生产代码未改动；未调用真实模型或搜索服务。

## 范围与预期

| 测试文件 | 预期 |
|---|---|
| `test_observability_fields.py` | 执行器产出 sources / completed，事件来源和耗时正确 |
| `test_quick_mode.py` | quick 模式生成包含真实测试摘要的报告 |
| `test_stream_observability.py` | 必须产出工具事件，run_id / timestamp / task channel 正确 |
| `test_stream_observability_round2.py` | 必须产出工具事件，task_run_id 与存储记录正确 |
| `test_stream_runner.py` | 正常分支收到 sources；错误分支收到预设的 boom，而不是签名 TypeError |
| `test_stream_runner_concurrency.py` | 10 个任务执行、并发上限 3；必须正常结束才算通过 |

6 个替身增加显式 `stop_event: Event | None = None`；已有取消专用替身和同步专用替身不需要修改。3 条新增工具事件存在性断言防止仅靠失败事件元数据假通过。

## 修复前后结果

| 阶段 | 实际结果 |
|---|---|
| 初次将 6 个文件一起运行 | 并发用例停顿，手动终止本次测试进程；没有完整计数，不算通过 |
| 加强断言后、修复替身前，运行前 5 个文件 | **8 failed, 2 passed**；均由替身拒绝 `stop_event` 导致 |
| 修复替身后，前 5 个文件 + v0.0.2 的 3 个回归文件 | **40 passed, 1 warning，1.55 秒** |
| 第 6 个并发文件，独立进程限时 15 秒 | **TIMEOUT**，进程树已停止；没有 pytest 通过结果 |
| 全量 `tests -x`，补依赖前 | **1 failed, 34 passed**；缺少可选 `redis` 包 |
| 补齐本地 redis 后，全量 `tests -x` | **1 failed, 59 passed**；内存/SQLite 存储类型假设冲突 |

通过用例的警告来自 HelloAgents/Pydantic 弃用配置；全量运行另外有 FastAPI 生命周期接口弃用警告。

## 可重复命令

从仓库根目录进入 `backend` 后执行：

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_observability_fields.py tests/test_quick_mode.py tests/test_stream_observability.py tests/test_stream_observability_round2.py tests/test_stream_runner.py tests/test_fact_check_service.py tests/test_task_executor_fact_check.py tests/test_stream_events.py -q --tb=short
```

重做红阶段：在独立临时工作区检出 `v0.0.2`，只加本版 3 条工具事件断言，运行上述前 5 个文件；预期 8 failed / 2 passed。不要回退当前工作区文件。

本次补齐了项目已声明的可选测试依赖（仅本地环境，实际安装 `redis==8.1.0`，未改依赖声明与锁文件）：

```powershell
uv pip install --python .venv-test/Scripts/python.exe "redis>=5.0.0"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q -x --tb=short
```

### 并发用例有界复现（Windows）

`faulthandler_timeout` 只打印堆栈，不会终止测试；因此另外使用父进程 15 秒截止。以下命令仅停止自己启动的测试子进程树：

```powershell
@'
import subprocess
import sys

command = [sys.executable, '-m', 'pytest', '-o', 'pythonpath=src .',
           '-o', 'faulthandler_timeout=5',
           'tests/test_stream_runner_concurrency.py', '-q', '--tb=short']
process = subprocess.Popen(command, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8')
try:
    output, _ = process.communicate(timeout=15)
    print(output)
    raise SystemExit(process.returncode)
except subprocess.TimeoutExpired:
    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                   capture_output=True, check=False)
    output, _ = process.communicate(timeout=5)
    print(output)
    print('TIMEOUT: concurrency test exceeded 15 seconds; child process tree stopped.')
    raise SystemExit(124)
'@ | .\.venv-test\Scripts\python.exe -
```

## 剩余问题与证据

### 1. 并发完成通知可能丢失（下一版优先）

5 秒堆栈显示主线程停在 `stream_runner.py` 的 `_run_task_workers → event_queue.get()`，3 个线程池 worker 均等待新任务；15 秒仍未结束。

静态检查发现：主循环收到一个 `__task_done__` 时只计数一次，随后 `_drain_public_events()` 可能从队列取走其他完成通知并直接丢弃，未累计 `finished_workers`。多条完成通知同批入队时，计数可能永远小于任务数。

`git diff v0.0.2 -- backend/src/services/stream_runner.py` 为空，该路径在此前版本已存在。堆栈与这一机制相符，但本轮未做控制调度的确定性复现，下一版应先建立固定事件顺序的回归用例再修复。不能将本次限时失败算成并发上限测试通过。

### 2. 运行存储测试依赖默认配置

全量首个失败：`tests/test_research_runs_api.py::test_research_run_endpoint_reads_shared_app_run_store`。

测试断言应用使用 `InMemoryResearchRunStore`，当前环境实际创建 `SQLiteResearchRunStore`。本轮未调整应用配置或该测试，也未逐项检查之后的测试；需要后续显式隔离测试配置。该失败不属于此次替身签名修复范围。

## 结论

本版已恢复 5 个文件的相关行为回归并加强 3 项断言；6 个替身均已对齐接口。并发和全量测试仍有明确阻塞，不能宣称全量通过。未运行前端构建、联网研究评估或生产发布。既有根目录 `data/` 保留且不提交。
