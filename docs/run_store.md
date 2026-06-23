# Research Run Store

本文件说明阶段四新增的研究运行记录存储设计。

## 目标

阶段三已经为流式研究流程增加了：

- `run_id`
- `timestamp`
- `task_run_id`
- `/research/runs/{run_id}` 查询接口
- 前端 Timeline 过滤

阶段四的目标是把运行时间线从纯内存升级为可持久化存储，让研究运行记录在服务重启后仍可查询。

## 存储接口

后端通过 `ResearchRunStore` Protocol 抽象运行记录存储：

```python
class ResearchRunStore(Protocol):
    def start_run(self, *, run_id: str, topic: str) -> None: ...
    def record_event(self, run_id: str, event: dict[str, Any]) -> None: ...
    def complete_run(self, run_id: str) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...
```

接口保持稳定，具体实现可以替换。

## 当前实现

文件：

```text
backend/src/services/research_run_store.py
```

当前有两个实现：

```text
InMemoryResearchRunStore
SQLiteResearchRunStore
```

### InMemoryResearchRunStore

适合：

- 本地调试
- 单进程临时运行
- 单元测试

限制：

- 服务重启后数据丢失
- 多进程/多 worker 不共享

### SQLiteResearchRunStore

适合：

- 本地开发持久化
- 轻量部署
- 服务重启后继续查询 run 历史

特点：

- 自动创建数据库目录和表
- `start_run()` 会替换同名 run，并清空旧事件
- `record_event()` 会忽略不存在的 run
- `get_run()` 按事件写入顺序返回完整 Timeline

## SQLite 表结构

```text
research_runs
  run_id TEXT PRIMARY KEY
  topic TEXT NOT NULL
  status TEXT NOT NULL

research_events
  id INTEGER PRIMARY KEY AUTOINCREMENT
  run_id TEXT NOT NULL
  event_type TEXT NOT NULL
  timestamp TEXT
  payload_json TEXT NOT NULL
```

事件 payload 原样以 JSON 字符串保存到 `payload_json`。

## 配置方式

默认使用内存 store：

```text
RUN_STORE_BACKEND=memory
```

启用 SQLite：

```text
RUN_STORE_BACKEND=sqlite
RUN_STORE_DB_PATH=./data/research_runs.sqlite3
```

Docker 部署时 `docker-compose.yml` 会显式覆盖为容器内持久化路径：

```text
RUN_STORE_BACKEND=sqlite
RUN_STORE_DB_PATH=/app/src/data/research_runs.sqlite3
```

并通过 `run_store_data:/app/src/data` volume 保留数据库文件。

也可以在代码里通过 `Configuration` 配置：

```python
config = Configuration(
    run_store_backend="sqlite",
    run_store_db_path="./data/research_runs.sqlite3",
)
```

## 应用级共享 store

FastAPI 应用启动时会创建一个应用级 `run_store`：

```python
app.state.run_store = _create_run_store_from_config(Configuration.from_env())
```

流式研究接口和查询接口共享同一个 store：

```text
POST /research/stream       写入 app.state.run_store
GET  /research/runs/{run_id} 读取 app.state.run_store
```

这样可以保证刚刚运行的研究可以立即通过 run_id 查询。

## 测试覆盖

相关测试：

```text
backend/tests/test_sqlite_research_run_store.py
backend/tests/test_research_run_store.py
backend/tests/test_research_services_factory.py
backend/tests/test_research_runs_api.py
```

覆盖行为：

- SQLite store 跨实例持久化
- 缺失 run 返回 None
- 缺失 run 的事件被忽略
- 同名 run 重新 start 时清空旧事件
- 非 JSON 事件 payload 会抛出 TypeError
- factory 根据配置选择 memory/sqlite
- FastAPI app 根据环境变量创建应用级 SQLite store

## 学习重点

阶段四的重点不是增加 Agent 智能，而是学习 Agent 工程地基：

- 通过 Protocol 抽象存储接口
- 通过依赖注入替换具体实现
- 用 SQLite 持久化事件时间线
- 让 `/research/runs/{run_id}` 在服务重启后仍有价值
- 保持 TDD：先写失败测试，再实现最小代码

## 后续方向

可以继续扩展，但建议顺序是“先可观测，再能力扩展”：

1. 增加 `started_at` / `completed_at` / `error` 字段
2. 增加 `duration_ms`，记录整次运行和关键阶段耗时
3. 增加 `fail_run(run_id, error)`
4. 支持分页查询 events
5. 支持按 topic / status 查询历史 run 列表
6. 为 Trace 面板提供按 `run_id` / `task_run_id` / `stream_token` 聚合后的事件视图
7. 为 Timeline 面板提供按 `timestamp` 排序、带 `duration_ms` 的事件视图
8. 将 SQLite store 升级为 PostgreSQL store
