# v0.1.0：单任务 Agent 决策循环

## 版本范围

- 日期：2026-09-17；基线：`v0.0.13` / `2eb1848`。
- 这是一次功能版本升级：把 v0.0.13 的 `search/finish` 契约接入实际任务执行，同时保留 fixed 固定搜索流程作为默认兼容路径。
- 新增 `DecisionLoop`：模型选择动作 → 执行一次搜索 → 形成有限观察 → 再选择动作。每个任务独立保存状态，不与并发任务共享查询集合或证据集合。
- 新增硬边界：最大 1～12 步、总时限 1～600 秒、单次决策时限 1～120 秒；重复查询、非法动作、决策异常、无证据 finish、取消和超时都有明确停止原因。
- 搜索结果只向决策器提供受限观察：最多 20 个 HTTP/HTTPS 来源，每个内容最多 2000 字符，按 URL 去重；错误记录只保留异常类型，不回传供应商异常正文。
- `LLMTaskDecider` 仅负责把有限上下文编码为 JSON 并调用模型，动作验证和工具执行仍由程序边界控制。决策模式通过 REST `execution_mode=decision` 或前端“决策循环（search / finish）”入口启用，自动使用 quick 单任务入口。
- 决策过程以 `status` 事件（`source=decision_loop`）记录，任务序列化结果保留 `decision_trace` 与 `decision_stop_reason`，便于回放和后续评估。

## 验收用例

后端新增 12 项：

- 空结果后改写查询，再以 finish 结束并保留证据；
- 非法动作、无证据 finish、重复查询和最大步数终止；
- 决策时限到期后不执行搜索；
- 取消在动作与搜索边界传播；
- 搜索异常转为类型化观察；来源 URL 去重、协议过滤、内容截断；
- fixed 路径不受决策模式改动影响；决策配置从环境变量解析；TaskExecutor 与服务工厂接入模型决策器；同步和流式任务都完成一次总结。

环境：Windows，Python 3.11.14，pytest 9.0.3，现有 `.venv-test`；决策循环单元和集成测试均使用确定性替身，不调用真实模型或联网搜索。

## 实际验证结果

- 实现前集成测试：**4 failed，1 warning，2.02 秒**；TaskExecutor 尚不接受 decision_provider，也没有服务工厂接线。
- 决策循环与集成相关测试：**34 passed，1 warning，1.70 秒**。
- 后端全量 `tests`：**196 passed，21 warnings，6.67 秒**；父进程 45 秒上限未触发，无中止。
- 前端 Vitest：**3 个测试文件、8 项通过，0.32 秒**。
- 前端生产构建：`vue-tsc --noEmit && vite build` 成功，120 个模块完成转换。
- 警告为既有 Pydantic/FastAPI 弃用提示。`git diff --check` 通过。

## 复现命令

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_decision_loop.py tests/test_decision_integration.py tests/test_task_actions.py -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings

cd ..\frontend
npm test -- --run
npm run build
```

环境变量启用示例：`TASK_EXECUTION_MODE=decision`，可选 `DECISION_MAX_STEPS=4`、`DECISION_TOTAL_TIMEOUT_SECONDS=90`、`DECISION_TIMEOUT_SECONDS=20`。HTTP 请求可传 `execution_mode: "decision"`；研究 `mode` 仍表示 deep/quick 流程模式。

## 边界与后续

本版本验证的是受限决策循环的程序契约与流程行为，不代表真实模型的研究质量。LLM 输出必须是已解码 JSON；不自动修补 Markdown、JSON 字符串或工具调用。finish 只表示停止收集，不代表证据已经支持结论。搜索 SDK 的底层线程仍不能被强制终止；每次搜索的超时停止信号只阻止支持该信号的后续重试。

决策循环当前运行在单个已有任务内，尚未动态修改 Todo 依赖图、委派多 Agent、恢复中断状态或使用质量评分自动重规划。下一阶段可用固定材料建立动作级评估集，比较 fixed 与 decision 的搜索次数、证据覆盖和错误停止率，再决定是否扩大默认使用范围。

分支 `codex/v0.1.0-agent-decision-loop`，本地 annotated tag `v0.1.0`；未推送或发布包。原有未跟踪 `data/` 保留且不提交。
