# v0.0.2 Test：事实核对的来源匹配回归

## 环境与范围

- 日期：2026-09-16。
- 修复前基线：`42261c4`，业务代码与此前 `b3729c0` 一致。
- Windows，Python 3.11.14，pytest 9.0.3，使用现有 `backend/.venv-test`。
- 业务改动：`FactCheckService.check()` 移除摘要自匹配条件，术语只对来源文本匹配。
- 固定材料与 mock 工具，不需要真实模型或搜索请求；未做联网研究质量评估。

## 用例与预期

| 场景 | 关键预期 |
|---|---|
| 4 个英文术语均在来源中，大小写不同 | `passed=True`、100 分、无缺词与警告 |
| 有 URL 的无关来源，摘要长度充足 | `passed=False`、4 个缺词、68 分；没有缺 URL/摘要短等干扰因素 |
| 来源缺 1 个术语 | 按原容忍阈值通过、返回该缺词、92 分 |
| 来源缺 2 个术语 | 按原容忍阈值失败、返回两个缺词、84 分 |
| 中文短语全部支持 / 来源无关 | 分别通过 / 失败；无关时返回 4 个中文缺词 |
| 缺少来源且摘要短 | 保留原有不通过和警告行为 |
| 执行器流式集成：支持 / 无关来源 | `fact_check_result` 正确传递判断和缺词，先于任务终态发出；核对失败不将任务改为失败 |
| 公开事件模型 | 既有事件契约测试继续通过 |

相关测试文件：

- [test_fact_check_service.py](../../../backend/tests/test_fact_check_service.py)
- [test_task_executor_fact_check.py](../../../backend/tests/test_task_executor_fact_check.py)
- [test_stream_events.py](../../../backend/tests/test_stream_events.py)

## 红 → 绿的实际结果

1. 修改测试前：原两个相关测试文件 **3 passed**。
2. 新增/强化测试，尚未改生产代码：两个文件 **5 failed, 4 passed**。失败覆盖英文无关来源、两种部分缺词、中文无关来源和执行器负例；旧实现把缺失术语当成已匹配。
3. 删除自匹配条件后：上述两个文件连同事件契约测试 **30 passed, 1 warning，2.46 秒**。
4. 独立审查复验相同三个文件：**30 passed**。

警告来自 HelloAgents 使用已弃用的 Pydantic class-based config；本版本未升级依赖。

## 可重复命令

从仓库根目录执行，现有 Windows 测试环境已安装依赖：

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_fact_check_service.py tests/test_task_executor_fact_check.py tests/test_stream_events.py -q
```

其他环境在安装后端及 pytest 后，可使用 `python -m pytest` 运行相同参数。`pythonpath` 中的 `src` 与 `.` 均相对 pytest 配置根目录 `backend`。

要重做红阶段，可在独立临时工作区检出 `42261c4`，只应用本版本两个测试文件的改动，再运行这两个文件，预期 5 项失败；不要在当前工作区回退已完成代码。

## 扩大回归与阻塞

全量命令：在 `backend` 执行 `.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q`。

- 首次从项目根目录运行时，错误使用 `pythonpath=backend/src`，导致 `evals` / `tests` 无法导入；纠正为以上目录和参数后完成收集。这是测试入口问题，不是业务回归。
- 完整运行出现多项失败且迟迟未结束，已终止本次测试进程，**没有完整通过率或最终用例总数**。
- 使用相同命令加 `-x --tb=short` 定位首个失败：**1 failed, 26 passed**。
- 失败用例：`tests/test_observability_fields.py::test_stream_runner_emits_source_and_duration_for_traceable_events`。
- 原因：`FakeTaskExecutor.execute()` 不接受调用方传入的 `stop_event`，未产生预期 `sources` 事件，随后触发 `StopIteration`。
- 在独立临时 Git worktree 检出 **`42261c4`** 后运行同一失败用例：**1 failed**，异常一致。临时工作区已移除。

其余全量运行中观察到的失败和停顿尚未逐项归因。本版只对上述首个阻塞做了基线对照，不声称所有失败均已证明与改动无关。

## 结论与边界

本次摘要自匹配修复的相关用例通过，接口兼容；全量测试基线仍需后续小版本修复。

规则仍按词项出现判断，不能识别同词反义、否定关系、数字冲突或独立来源可信度。`matched_sources` 仍可能回退为已有 URL，因此不能当作事实已获支持的证据清单。未执行前端构建、真实 LLM/API、生产部署或 Python/npm 包发布。
