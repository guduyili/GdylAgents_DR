"""
工具调用事件记录链路 —— 流程演示测试

本文件不依赖 LLM/网络，完全用 Mock 模拟真实调用链，逐步展示：

  Step 1  ToolCallTracker 初始化
  Step 2  模拟 ToolAwareSimpleAgent 触发 tool_call_listener
  Step 3  record() 内部解析（task_id 三级推断 + note_id 提取）
  Step 4  同步模式：drain() 消费事件并写回 TodoItem
  Step 5  流式模式：event_sink 实时回调 → 入队
  Step 6  并发安全：多线程同时触发 record()
  Step 7  游标机制：多次 drain() 只取增量

运行方式：
  cd GdylAgents_DR/backend/src
  python test_tool_call_chain.py
  python test_tool_call_chain.py --step 3   # 只运行 Step 3
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from queue import Queue

sys.path.insert(0, str(Path(__file__).parent))

from models import SummaryState, TodoItem
from services.tool_events import ToolCallEvent, ToolCallTracker

# ─────────────────────────────────────────────
# 打印工具
# ─────────────────────────────────────────────
SEP = "─" * 60
THICK = "═" * 60


def header(title: str) -> None:
    print(f"\n{THICK}")
    print(f"  {title}")
    print(THICK)


def section(label: str) -> None:
    print(f"\n{SEP}")
    print(f"  {label}")
    print(SEP)


def ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def info(msg: str) -> None:
    print(f"  ℹ️   {msg}")


def show_event(event: dict, indent: int = 2) -> None:
    pad = " " * indent
    for k, v in event.items():
        val = str(v)
        if len(val) > 80:
            val = val[:80] + "..."
        print(f"{pad}{k:20s} = {val}")


# ─────────────────────────────────────────────
# 构造辅助：模拟 ToolAwareSimpleAgent 的 payload
# ─────────────────────────────────────────────
def _make_payload(
    agent_name: str,
    tool_name: str,
    parsed_parameters: dict,
    result: str,
    raw_parameters: str = "",
) -> dict:
    """构造与真实 ToolAwareSimpleAgent 一致的 tool_call_listener payload。"""
    return {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "raw_parameters": raw_parameters or str(parsed_parameters),
        "parsed_parameters": parsed_parameters,
        "result": result,
    }


# ══════════════════════════════════════════════════════════════════
# Step 1  ToolCallTracker 初始化
# ══════════════════════════════════════════════════════════════════
def step1_init() -> ToolCallTracker:
    header("Step 1 ▶  ToolCallTracker 初始化")

    notes_workspace = "/tmp/test_notes"
    tracker = ToolCallTracker(notes_workspace=notes_workspace)

    info(f"notes_workspace = {tracker._notes_workspace}")
    info(f"_events         = {tracker._events}   (空列表)")
    info(f"_cursor         = {tracker._cursor}   (游标初始为 0)")
    info(f"_event_sink     = {tracker._event_sink}   (流式回调，默认 None)")
    info(f"_lock           = {tracker._lock}   (线程锁)")

    ok("ToolCallTracker 初始化完成")
    return tracker


# ══════════════════════════════════════════════════════════════════
# Step 2  模拟 Agent 触发 tool_call_listener → record()
# ══════════════════════════════════════════════════════════════════
def step2_record_basic(tracker: ToolCallTracker) -> None:
    header("Step 2 ▶  模拟 Agent 触发 tool_call_listener → record()")

    info("场景：任务总结专家调用 note 工具创建笔记，参数中直接含 task_id=1")

    payload = _make_payload(
        agent_name="任务总结专家",
        tool_name="note",
        parsed_parameters={
            "action": "create",
            "task_id": 1,
            "title": "AI Agent 技术趋势 - 任务1总结",
            "note_type": "summary",
            "tags": ["task_1", "ai_agent"],
            "content": "## 总结内容\n这是任务1的总结。",
        },
        result="✅ 笔记创建成功\nID: note_20260512_001\n标题: AI Agent 技术趋势 - 任务1总结",
    )

    # breakpoint()
    print("\n  [payload 传入 record()]")
    show_event(payload)
    # breakpoint()
    tracker.record(payload)

    print(f"\n  [record() 执行后]")
    info(f"_events 长度     = {len(tracker._events)}")
    e = tracker._events[0]
    info(f"事件 id          = {e.id}")
    info(f"agent            = {e.agent}")
    info(f"tool             = {e.tool}")
    info(f"task_id          = {e.task_id}   (从 parsed_parameters['task_id'] 提取)")
    info(f"note_id          = {e.note_id}   (从 result 文本 'ID: note_20260512_001' 提取)")
    ok("record() 完成")


# ══════════════════════════════════════════════════════════════════
# Step 3  task_id 三级推断 + note_id 正则提取
# ══════════════════════════════════════════════════════════════════
def step3_infer_task_id() -> None:
    header("Step 3 ▶  task_id 三级推断 + note_id 正则提取")

    tracker = ToolCallTracker(notes_workspace=None)

    cases = [
        {
            "desc": "方式1：parameters 中直接含 task_id 字段",
            "params": {"task_id": 2, "title": "任意标题"},
            "result": "✅ 笔记创建成功\nID: note_aaa",
            "expected_task_id": 2,
            "expected_note_id": "note_aaa",
        },
        {
            "desc": "方式2：parameters 中无 task_id，但 tags 包含 'task_3'",
            "params": {"title": "某标题", "tags": ["research", "task_3", "trend"]},
            "result": "✅ 笔记创建成功\nID: note_bbb",
            "expected_task_id": 3,
            "expected_note_id": "note_bbb",
        },
        {
            "desc": "方式3：parameters 中无 task_id/tags，但 title 含 '任务4'",
            "params": {"title": "任务4 的深度分析"},
            "result": "✅ 笔记创建成功\nID: note_ccc",
            "expected_task_id": 4,
            "expected_note_id": "note_ccc",
        },
        {
            "desc": "三种方式均无法推断（task_id=None）",
            "params": {"title": "无任务关联的笔记"},
            "result": "✅ 笔记创建成功\nID: note_ddd",
            "expected_task_id": None,
            "expected_note_id": "note_ddd",
        },
    ]

    all_pass = True
    for i, case in enumerate(cases, start=1):
        section(f"  子场景 {i}：{case['desc']}")
        payload = _make_payload(
            agent_name="任务总结专家",
            tool_name="note",
            parsed_parameters=case["params"],
            result=case["result"],
        )
        tracker.record(payload)
        e = tracker._events[-1]
        task_id_ok = e.task_id == case["expected_task_id"]
        note_id_ok = e.note_id == case["expected_note_id"]
        info(f"推断 task_id = {e.task_id}  期望={case['expected_task_id']}  {'✅' if task_id_ok else '❌'}")
        info(f"提取 note_id = {e.note_id}  期望={case['expected_note_id']}  {'✅' if note_id_ok else '❌'}")
        if not (task_id_ok and note_id_ok):
            all_pass = False

    if all_pass:
        ok("task_id 三级推断 + note_id 提取全部通过")
    else:
        print("  ❌  部分断言失败")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════
# Step 4  同步模式：drain() 消费事件并写回 TodoItem
# ══════════════════════════════════════════════════════════════════
def step4_sync_drain() -> None:
    header("Step 4 ▶  同步模式：drain() 消费事件并写回 TodoItem")

    tracker = ToolCallTracker(notes_workspace="/tmp/notes")

    # 构造两个任务
    task1 = TodoItem(id=1, title="任务1", intent="分析趋势", query="AI trends")
    task2 = TodoItem(id=2, title="任务2", intent="对比工具", query="AI tools")
    state = SummaryState(research_topic="AI Agent")
    state.todo_items = [task1, task2]

    info("初始状态：task1.note_id = None, task2.note_id = None")

    # 模拟 task1 的笔记调用
    tracker.record(_make_payload(
        agent_name="任务总结专家",
        tool_name="note",
        parsed_parameters={"action": "create", "task_id": 1, "title": "任务1总结"},
        result="✅ 笔记创建成功\nID: note_task1_001",
    ))
    # 模拟 task2 的笔记调用
    tracker.record(_make_payload(
        agent_name="任务总结专家",
        tool_name="note",
        parsed_parameters={"action": "create", "task_id": 2, "title": "任务2总结"},
        result="✅ 笔记创建成功\nID: note_task2_002",
    ))

    info(f"\n  drain() 前：_cursor = {tracker._cursor}, _events 长度 = {len(tracker._events)}")

    # 第一次 drain
    payloads = tracker.drain(state, step=1)

    info(f"  drain() 后：_cursor = {tracker._cursor}, 返回事件数 = {len(payloads)}")
    info(f"  task1.note_id = {task1.note_id}   (已写回 TodoItem)")
    info(f"  task1.note_path = {task1.note_path}")
    info(f"  task2.note_id = {task2.note_id}   (已写回 TodoItem)")
    info(f"  task2.note_path = {task2.note_path}")

    print("\n  [drain() 返回的 SSE 载荷]")
    for p in payloads:
        print(f"  {'─'*30}")
        show_event(p)

    # 第二次 drain 应返回空（游标机制）
    payloads2 = tracker.drain(state, step=1)
    info(f"\n  第二次 drain() 返回事件数 = {len(payloads2)}   (游标已推进，无增量)")

    assert task1.note_id == "note_task1_001", "❌ task1.note_id 写回失败"
    assert task2.note_id == "note_task2_002", "❌ task2.note_id 写回失败"
    assert len(payloads2) == 0, "❌ 第二次 drain 应返回空"
    ok("同步模式 drain() 测试通过")


# ══════════════════════════════════════════════════════════════════
# Step 5  流式模式：event_sink 实时回调 → 入队
# ══════════════════════════════════════════════════════════════════
def step5_stream_sink() -> None:
    header("Step 5 ▶  流式模式：event_sink 实时回调 → 入队")

    tracker = ToolCallTracker(notes_workspace="/tmp/notes")
    received: list[dict] = []
    event_queue: Queue = Queue()

    # 模拟 run_stream 中的 tool_event_sink
    def tool_event_sink(event: dict) -> None:
        print(f"  ⚡ [sink 触发] type={event.get('type')} tool={event.get('tool')} note_id={event.get('note_id')}")
        event_queue.put(event)
        received.append(event)

    # 注册 sink（进入流式模式）
    tracker.set_event_sink(tool_event_sink)
    info("已调用 set_event_sink()，进入流式模式")

    info("模拟 Agent 触发工具调用...")
    tracker.record(_make_payload(
        agent_name="任务总结专家",
        tool_name="note",
        parsed_parameters={"action": "create", "task_id": 1, "title": "流式任务总结"},
        result="✅ 笔记创建成功\nID: note_stream_001",
    ))

    info(f"\n  sink 已接收事件数 = {len(received)}")
    info(f"  event_queue 大小  = {event_queue.qsize()}")
    print("\n  [sink 收到的事件]")
    show_event(received[0])

    # 取消注册（流结束）
    tracker.set_event_sink(None)
    info("\n  已调用 set_event_sink(None)，退出流式模式")

    # 流式模式下 drain() 应返回空（事件已由 sink 推送）
    state = SummaryState(research_topic="test")
    state.todo_items = []
    drained = tracker.drain(state)
    info(f"  drain() 返回事件数 = {len(drained)}   (流式模式事件由 sink 处理，drain 不重复)")

    assert len(received) == 1, "❌ sink 应接收 1 个事件"
    ok("流式模式 event_sink 测试通过")


# ══════════════════════════════════════════════════════════════════
# Step 6  并发安全：多线程同时触发 record()
# ══════════════════════════════════════════════════════════════════
def step6_concurrent_safety() -> None:
    header("Step 6 ▶  并发安全：多线程同时触发 record()")

    tracker = ToolCallTracker(notes_workspace=None)
    N = 10  # 模拟 10 个任务线程

    info(f"启动 {N} 个线程，每个线程各调用一次 record()...")

    def worker(task_id: int) -> None:
        time.sleep(0.01)  # 让线程尽量同时触发
        tracker.record(_make_payload(
            agent_name="任务总结专家",
            tool_name="note",
            parsed_parameters={"action": "create", "task_id": task_id, "title": f"任务{task_id}总结"},
            result=f"✅ 笔记创建成功\nID: note_concurrent_{task_id:02d}",
        ))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, N + 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    info(f"所有线程执行完毕")
    info(f"_events 长度     = {len(tracker._events)}  (期望 {N})")
    info(f"事件 id 列表     = {[e.id for e in tracker._events]}")
    info(f"task_id 集合     = {sorted(e.task_id for e in tracker._events if e.task_id is not None)}")

    ids = [e.id for e in tracker._events]
    assert len(ids) == N, f"❌ 事件数不对，期望 {N}，实际 {len(ids)}"
    assert len(set(ids)) == N, "❌ 存在重复 id，线程不安全！"
    ok(f"并发 {N} 线程写入，无数据竞争，无重复 id")


# ══════════════════════════════════════════════════════════════════
# Step 7  游标机制：多次 drain() 只取增量
# ══════════════════════════════════════════════════════════════════
def step7_cursor_increment() -> None:
    header("Step 7 ▶  游标机制：多次 drain() 只取增量")

    tracker = ToolCallTracker(notes_workspace=None)
    state = SummaryState(research_topic="test")
    state.todo_items = []

    info("第1轮：写入 2 个事件，drain 一次")
    for i in range(1, 3):
        tracker.record(_make_payload(
            agent_name="规划专家", tool_name="note",
            parsed_parameters={"task_id": i, "title": f"任务{i}"},
            result=f"✅ 笔记创建成功\nID: note_{i:02d}",
        ))
    d1 = tracker.drain(state)
    info(f"  drain #1 返回 {len(d1)} 个事件   _cursor={tracker._cursor}")

    info("第2轮：再写入 3 个事件，drain 一次（应只得到新增的 3 个）")
    for i in range(3, 6):
        tracker.record(_make_payload(
            agent_name="总结专家", tool_name="note",
            parsed_parameters={"task_id": i, "title": f"任务{i}"},
            result=f"✅ 笔记创建成功\nID: note_{i:02d}",
        ))
    d2 = tracker.drain(state)
    info(f"  drain #2 返回 {len(d2)} 个事件   _cursor={tracker._cursor}")
    info(f"  d2 中的 note_id = {[p.get('note_id') for p in d2]}")

    info("第3轮：不写入任何事件，drain 应返回空")
    d3 = tracker.drain(state)
    info(f"  drain #3 返回 {len(d3)} 个事件   (期望 0)")

    assert len(d1) == 2, f"❌ drain #1 期望 2，实际 {len(d1)}"
    assert len(d2) == 3, f"❌ drain #2 期望 3，实际 {len(d2)}"
    assert len(d3) == 0, f"❌ drain #3 期望 0，实际 {len(d3)}"
    ok("游标机制验证通过，多次 drain 只取增量")


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════
ALL_STEPS = {
    "1": ("ToolCallTracker 初始化", lambda: step1_init()),
    "2": ("模拟 Agent 触发 record()", lambda: step2_record_basic(step1_init())),
    "3": ("task_id 三级推断 + note_id 提取", step3_infer_task_id),
    "4": ("同步模式 drain()", step4_sync_drain),
    "5": ("流式模式 event_sink", step5_stream_sink),
    "6": ("并发安全", step6_concurrent_safety),
    "7": ("游标机制增量消费", step7_cursor_increment),
}


def run_all() -> None:
    tracker = step1_init()
    step2_record_basic(tracker)
    step3_infer_task_id()
    step4_sync_drain()
    step5_stream_sink()
    step6_concurrent_safety()
    step7_cursor_increment()

    print(f"\n{THICK}")
    print("  🎉  所有 Step 执行完毕，工具调用事件记录链路验证通过！")
    print(THICK)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="工具调用事件记录链路演示测试")
    parser.add_argument(
        "--step",
        choices=list(ALL_STEPS.keys()),
        default=None,
        help="只运行指定 Step（1-7），默认运行全部",
    )
    args = parser.parse_args()

    if args.step:
        name, fn = ALL_STEPS[args.step]
        print(f"\n单独运行 Step {args.step}：{name}")
        fn()
    else:
        run_all()
