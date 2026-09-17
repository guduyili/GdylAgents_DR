# v0.0.7：DuckDuckGo 请求共享时间预算

## 范围

- 日期：2026-09-16；基线：`v0.0.6` / `f1a97b5`。
- 原问题：DuckDuckGo 的 lite/api/html 三次尝试均固定传入 15 秒超时，未使用 `search_timeout_seconds`，调用方超时后仍可能继续发起后续尝试。
- 修复：适配器传入配置预算，内部建立单调时钟截止时间。每次 DDGS 调用使用 `min(15, 剩余秒数)`，预算耗尽则停止下一次尝试并记录提示。
- 保留既有回退顺序与结果格式；直接调用内部 helper 的默认预算为 45 秒。其他提供商与全局回退链本轮不改。

## 验证

Windows，Python 3.11.14，pytest 9.0.3；使用现有 `.venv-test`。用假 DDGS 客户端及可控时钟，不等待真实时间或联网。

| 新用例 | 预期 |
|---|---|
| 2 秒预算，两次失败分别耗时 0.75 / 1.25 秒 | 超时参数为 2 / 1.25，不启动第三次，返回预算耗尽提示 |
| 第一次空结果耗时 0.25 秒，第二次成功 | 第二次仅剩 1.75 秒，结果正常返回 |
| 60 秒预算，第一次失败后第二次成功 | 两次单次超时仍限制为 15 秒 |
| 1 秒预算，第一次耗时 0.75 秒 | 第二次收到 0.25 秒超时参数 |

同时验证每次客户端上下文都执行退出路径；这不等价于验证 SDK 已释放全部内部资源。已对照当前安装的 DDGS/HTTP 客户端源码与 primp 类型声明确认超时传递路径，未升级依赖。

- 修复前新增用例：**3 failed, 1 passed, 3 deselected**。旧实现仍传入 15 秒，耗尽后也继续第三次尝试。
- 修复后完整 `backend/tests`：**131 passed, 21 warnings，7.06 秒**。父进程 45 秒截止未触发。
- 警告为已有 Pydantic/FastAPI 弃用提示。

## 复现

```powershell
cd backend
$env:PYTHONIOENCODING = "utf-8"
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests/test_search_backends.py -k shares_budget -q --tb=short --disable-warnings
.\.venv-test\Scripts\python.exe -m pytest -o "pythonpath=src ." tests -q --tb=short --disable-warnings
```

红阶段可在独立工作区检出 `v0.0.6`，仅应用本版新增测试再运行第一条命令。全量限时方法沿用 [v0.0.3](../v0.0.3/test.md) 的父进程方式，测试目标为 `tests`、上限 45 秒。

## 边界与下一步

本版保证适配器传入剩余预算，并在预算耗尽后停止启动 DDGS 的后续尝试。SDK 的初始化、多请求、内部线程等待及退出耗时可能另有边界，不能宣称真实调用严格在预算内结束，也未验证公网行为或资源完全回收。

跨 Tavily、DuckDuckGo 等提供商的 `FallbackSearchBackend` 尚未共享全链路截止时间，取消信号也未传入各 SDK。下一版优先限制预算耗尽后的跨后端回退，再评估底层取消与资源释放。

本地分支 `codex/v0.0.7-ddgs-deadline`，标签 `v0.0.7`；不推送、不发布包，保留原有未跟踪 `data/`。
