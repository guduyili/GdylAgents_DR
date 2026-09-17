# v0.0.13：单任务 search/finish 动作契约

## 范围与设计

- 日期：2026-09-17；基线：`v0.0.12` / `218711f`。
- 沿学习主线 A 增加独立 `services.task_actions` 模块，供后续单任务决策循环使用；当前生产流程尚未调用该模块。
- 使用现有 Pydantic，以 action 为区分字段，只允许 search 和 finish。search 必须包含 query、reason；finish 只包含 reason。所有字段显式必填，拒绝多余字段与类型转换。
- query/reason 去除首尾空白后必须为 1～512 个字符。reason 是可观察的简短决策说明，不要求模型输出内部推理。模型冻结，避免正常属性赋值绕过校验。
- `parse_task_action` 校验已解码的动作数据，返回 SearchAction 或 FinishAction；无效数据抛 ValidationError。原始 JSON 字符串、Markdown 包装不自动解析或修补。

最小使用示例：

```python
from services.task_actions import parse_task_action

action = parse_task_action({
    "action": "search", "query": "Agent 工具调用", "reason": "补充来源",
})
finish = parse_task_action({"action": "finish", "reason": "已有足够证据"})
```

动作校验属于工具调用之前的程序边界。finish 只是结束资料收集的提议，不证明证据充分，也不会直接把 TodoItem 标记为 completed。

## 测试与结果

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`，无新依赖、模型或网络调用。

新增 22 项测试：正常搜索与结束、中文和首尾空白规范化、512 字符边界、输入不变与属性不可赋值；拒绝未知动作、大小写变体、缺字段、纯空白、513 字符、错误类型、额外工具/查询字段、列表、JSON 文本与 None。

- 实现前：**1 collection error，0.41 秒**，模块尚不存在；不能将其描述为 22 项断言失败。
- 实现后动作测试：**22 passed，0.18 秒**。
- 首轮后端全量：**1 failed, 182 passed, 21 warnings，7.84 秒**。旧的无搜索结果测试使用真实时钟，却要求 duration_ms 精确等于 0，本次实际为 16。
- 对照 `git show v0.0.12:backend/tests/test_task_executor.py`，确认旧版本已有该真实时钟与零耗时断言组合；本版动作模块未接入 TaskExecutor。给该测试注入固定单调时钟，保留所有原断言，不修改生产耗时计算。
- 修正时钟后后端全量：**183 passed, 21 warnings，6.52 秒**。两轮均采用父进程 45 秒上限，无超时中止。
- 警告为既有 Pydantic/FastAPI 弃用提示。经验记录：需要精确比较 duration_ms 的事件测试应注入确定性时钟；真实等待/超时行为由专门的并发测试验证。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_task_actions.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

实现前复现：独立工作区检出 `v0.0.12`，仅应用新增动作测试并运行。旧时钟测试的失败依赖实际调度耗时，不能承诺每次复现。全量限时沿用 [v0.0.3](../v0.0.3/test.md) 的父进程封装，目标 `tests`、上限 45 秒。

## 边界与下一步

本版是契约基础，不是已运行的自主 Agent。没有模型输出接入、工具执行、循环轮数限制、重复查询检测、证据充分性判断或线上 API 改动；未验证前端、联网研究与真实模型效果。512 字符是本实验的初始边界，并非外部搜索服务限制。

下一版实现有最大步数的单任务决策循环，通过注入决策器与搜索执行器，验证 search → 观察结果 → finish，以及非法动作与步数耗尽；先以确定性替身验证，再接模型。

分支 `codex/v0.0.13-task-action-contract`，本地 annotated tag `v0.0.13`。未推送或发布包；原有未跟踪 `data/` 保留且不提交。
