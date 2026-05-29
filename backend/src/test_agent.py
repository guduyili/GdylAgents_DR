"""
测试 DeepResearchAgent.run() 和 run_stream() 的完整调用
运行方式：
  cd GdylAgents_DR/backend/src
  python test_agent.py          # 默认测试 run_stream
  python test_agent.py --mode run       # 测试同步 run
  python test_agent.py --mode stream    # 测试流式 run_stream
  python test_agent.py --mode both      # 两者都测
  python test_agent.py --topic "你的主题"
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

DEFAULT_TOPIC = "2026年 AI Agent 技术趋势"


# ══════════════════════════════════════════════════════════
# 测试 agent.run() — 同步模式
# ══════════════════════════════════════════════════════════
def test_run(topic: str) -> None:
    print("\n" + "═" * 60)
    print("测试 agent.run() — 同步模式")
    print("═" * 60)
    print(f"  研究主题: {topic}")
    print("  ⚠️  同步模式会阻塞直到所有任务完成，耗时较长\n")

    from agent import DeepResearchAgent

    agent = DeepResearchAgent()
    print(f"  [初始化] model         = {agent.llm.model}")
    print(f"  [初始化] report_model  = {agent.config.resolved_report_model()}")
    print(f"  [初始化] notes_ws      = {agent.config.notes_workspace}")
    print(f"  [初始化] note_tool     = {'✅' if agent.note_tool else '❌'}\n")

    t0 = time.time()
    result = agent.run(topic)
    elapsed = time.time() - t0

    print(f"\n  [结果] 总耗时         = {elapsed:.1f}s")
    print(f"  [结果] 任务数         = {len(result.todo_items)}")
    for t in result.todo_items:
        print(f"    [{t.id}] {t.title}")
        print(f"           status       = {t.status}")
        print(f"           summary_len  = {len(t.summary or '')} 字符")
        print(f"           note_id      = {t.note_id or '无'}")

    report = result.report_markdown or result.running_summary or ""
    print(f"\n  [报告] 长度           = {len(report)} 字符")
    print(f"  [报告] 预览           :\n{'─'*40}")
    print(report[:500])
    print("─" * 40)

    assert report, "❌ 报告为空！"
    print("\n  ✅ run() 测试通过")


# ══════════════════════════════════════════════════════════
# 测试 agent.run_stream() — 流式模式
# ══════════════════════════════════════════════════════════
def test_run_stream(topic: str) -> None:
    print("\n" + "═" * 60)
    print("测试 agent.run_stream() — 流式模式")
    print("═" * 60)
    print(f"  研究主题: {topic}\n")

    from agent import DeepResearchAgent

    agent = DeepResearchAgent()
    print(f"  [初始化] model         = {agent.llm.model}")
    print(f"  [初始化] report_model  = {agent.config.resolved_report_model()}")
    print(f"  [初始化] notes_ws      = {agent.config.notes_workspace}")
    print(f"  [初始化] note_tool     = {'✅' if agent.note_tool else '❌'}\n")

    event_counts: dict[str, int] = {}
    final_report = ""
    final_note_id = None
    task_summaries: dict[int, str] = {}

    t0 = time.time()

    for event in agent.run_stream(topic):
        etype = event.get("type", "unknown")
        event_counts[etype] = event_counts.get(etype, 0) + 1
        elapsed = time.time() - t0
        breakpoint()
        # ── 打印每类事件的关键信息 ──
        if etype == "status":
            print(f"  [{elapsed:6.1f}s] ▶ status       : {event.get('message', '')}")

        elif etype == "todo_list":
            tasks = event.get("tasks", [])
            print(f"  [{elapsed:6.1f}s] ▶ todo_list    : {len(tasks)} 个任务")
            for t in tasks:
                print(f"    [{t['id']}] {t['title']}")
                print(f"           query = {t.get('query', '')[:60]}")

        elif etype == "sources":
            tid = event.get("task_id")
            backend = event.get("backend", "?")
            src = str(event.get("latest_sources", ""))
            print(f"  [{elapsed:6.1f}s] ▶ sources      : task_id={tid} backend={backend}")
            if src:
                print(f"           来源预览: {src[:80]}")

        elif etype == "task_summary_chunk":
            # chunk 逐字输出，不逐条打印，只在第一条时提示
            if event_counts[etype] == 1:
                print(f"  [{elapsed:6.1f}s] ▶ summary_chunk: 开始流式输出...")

        elif etype == "task_status":
            tid = event.get("task_id")
            status = event.get("status")
            note_id = event.get("note_id") or "无"
            summary_len = len(event.get("summary") or "")
            task_summaries[tid] = event.get("summary") or ""
            print(f"  [{elapsed:6.1f}s] ▶ task_status  : task_id={tid} → {status}")
            print(f"           note_id     = {note_id}")
            print(f"           summary_len = {summary_len} 字符")

        elif etype == "tool_call":
            tool = event.get("tool_name", "?")
            agent_name = event.get("agent_name", "?")
            print(f"  [{elapsed:6.1f}s] ▶ tool_call    : {agent_name} → {tool}")

        elif etype == "final_report":
            final_report = event.get("report", "")
            final_note_id = event.get("note_id")
            print(f"\n  [{elapsed:6.1f}s] ✅ final_report 收到！")
            print(f"           report_len  = {len(final_report)} 字符")
            print(f"           note_id     = {final_note_id or '无'}")
            print(f"           报告预览    :")
            print("  " + "─" * 40)
            for line in final_report[:500].splitlines():
                print(f"  {line}")
            print("  " + "─" * 40)

        elif etype == "done":
            total = time.time() - t0
            print(f"\n  [{elapsed:6.1f}s] ▶ done         : 流程结束，总耗时 {total:.1f}s")

        elif etype == "error":
            print(f"  [{elapsed:6.1f}s] ❌ error        : {event.get('detail')}")
        breakpoint()

    # ── 汇总统计 ──
    print(f"\n  {'─'*40}")
    print(f"  事件统计:")
    for k, v in sorted(event_counts.items()):
        marker = "✅" if k in ("final_report", "done") else "  "
        print(f"  {marker}  {k:25s}: {v} 次")

    print(f"\n  任务摘要详情:")
    for tid, summary in task_summaries.items():
        print(f"    task_id={tid}: {len(summary)} 字符")
        if summary:
            print(f"    预览: {summary[:120]}")

    assert final_report, "❌ 未收到 final_report 事件，报告为空！"
    assert "done" in event_counts, "❌ 未收到 done 事件！"
    print("\n  ✅ run_stream() 测试通过")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 DeepResearchAgent run / run_stream")
    parser.add_argument("--mode", choices=["run", "stream", "both"], default="stream",
                        help="run=同步, stream=流式(默认), both=两者都跑")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="研究主题")
    args = parser.parse_args()

    print(f"\n研究主题: {args.topic}")
    print(f"测试模式: {args.mode}")

    try:
        if args.mode in ("run", "both"):
            test_run(args.topic)
        if args.mode in ("stream", "both"):
            test_run_stream(args.topic)
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
