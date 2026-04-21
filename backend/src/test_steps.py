"""
各模块独立验证脚本
运行方式：cd Gdylagent_DR/backend/src && python test_steps.py
可单独运行某一步：python test_steps.py --step 1
"""

import argparse
import sys
from pathlib import Path

# 确保 src 目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent))


# ──────────────────────────────────────────────
# 步骤1：验证数据模型 models.py
# ──────────────────────────────────────────────
def test_step1_models():
    print("\n===== 步骤1: models.py =====")
    from models import TodoItem, SummaryState, SummaryStateOutput

    # 创建一个任务
    task = TodoItem(id=1, title="测试任务", intent="验证数据结构", query="AI agent 2026")
    print(f"TodoItem 创建成功: {task}")
    assert task.status == "pending", "默认状态应为 pending"
    assert task.summary is None, "默认摘要应为 None"

    # 创建会话状态
    state = SummaryState(research_topic="AI Agent 学习路线")
    state.todo_items = [task]
    print(f"SummaryState 创建成功: research_topic={state.research_topic}, 任务数={len(state.todo_items)}")

    # 创建输出模型
    output = SummaryStateOutput(running_summary="测试摘要", todo_items=[task])
    print(f"SummaryStateOutput 创建成功: {output.running_summary}")
    print("✅ 步骤1 通过")


# ──────────────────────────────────────────────
# 步骤2：验证配置加载 config.py
# ──────────────────────────────────────────────
def test_step2_config():
    print("\n===== 步骤2: config.py =====")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from config import Configuration, SearchAPI

    config = Configuration.from_env()
    print(f"LLM 提供商:   {config.llm_provider}")
    print(f"模型 ID:      {config.resolved_model()}")
    print(f"API Key:      {'已设置' if config.llm_api_key else '❌ 未设置'}")
    print(f"Base URL:     {config.llm_base_url or '未设置（将使用默认值）'}")
    print(f"搜索后端:     {config.search_api}")
    print(f"研究循环上限: {config.max_web_research_loops}")

    # 验证 Ollama URL 补全逻辑
    test_cfg = Configuration(llm_provider="ollama", ollama_base_url="http://localhost:11434")
    assert test_cfg.sanitized_ollama_url().endswith("/v1"), "Ollama URL 应以 /v1 结尾"
    print("✅ 步骤2 通过")


# ──────────────────────────────────────────────
# 步骤3：验证搜索服务 services/search.py
# ──────────────────────────────────────────────
def test_step3_search():
    print("\n===== 步骤3: services/search.py =====")
    from services.search import _ddgs_search

    print("正在搜索 'AI agent 2026'（可能需要几秒）...")
    result = _ddgs_search("AI agent 2026", max_results=3)

    results = result.get("results", [])
    notices = result.get("notices", [])

    print(f"搜索后端: {result.get('backend')}")
    print(f"返回结果数: {len(results)}")

    if notices:
        for n in notices:
            print(f"  ⚠️ {n}")

    if results:
        print("第一条结果:")
        print(f"  标题: {results[0].get('title', '')[:60]}")
        print(f"  URL:  {results[0].get('url', '')}")
        print("✅ 步骤3 通过")
    else:
        print("❌ 未返回任何结果，请检查网络或更换搜索 backend")


# ──────────────────────────────────────────────
# 步骤4：验证规划服务 services/planner.py
# ──────────────────────────────────────────────
def test_step4_planner():
    print("\n===== 步骤4: services/planner.py =====")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from config import Configuration
    from models import SummaryState
    from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
    from prompts import todo_planner_system_prompt
    from services.planner import PlanningService

    config = Configuration.from_env()

    # 创建最简 LLM（不带工具注册表）
    llm = HelloAgentsLLM(
        model=config.resolved_model(),
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        temperature=0.0,
    )
    planner_agent = ToolAwareSimpleAgent(
        name="规划测试",
        llm=llm,
        system_prompt=todo_planner_system_prompt.strip(),
        enable_tool_calling=False,
    )

    planner = PlanningService(planner_agent, config)
    state = SummaryState(research_topic="2026年 AI Agent 学习路线")

    print(f"正在规划主题：{state.research_topic}")
    tasks = planner.plan_todo_list(state)

    print(f"规划出 {len(tasks)} 个任务:")
    for t in tasks:
        print(f"  [{t.id}] {t.title} — {t.intent[:40]}...")
    assert len(tasks) > 0, "至少应规划出 1 个任务"
    print("✅ 步骤4 通过")


# ──────────────────────────────────────────────
# 步骤5：验证总结服务 services/summarizer.py
# ──────────────────────────────────────────────
def test_step5_summarizer():
    print("\n===== 步骤5: services/summarizer.py =====")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from config import Configuration
    from models import SummaryState, TodoItem
    from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
    from prompts import task_summarizer_instructions
    from services.summarizer import SummarizationService

    config = Configuration.from_env()

    llm = HelloAgentsLLM(
        model=config.resolved_model(),
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        temperature=0.0,
    )

    def agent_factory():
        return ToolAwareSimpleAgent(
            name="总结测试",
            llm=llm,
            system_prompt=task_summarizer_instructions.strip(),
            enable_tool_calling=False,
        )

    summarizer = SummarizationService(agent_factory, config)
    state = SummaryState(research_topic="AI Agent 学习路线")

    # 构造一个模拟任务和搜索上下文
    task = TodoItem(id=1, title="能力框架", intent="梳理 AI Agent 核心能力模块", query="AI agent skills 2026")
    context = """
信息来源: IBM AI Agent Guide
URL: https://ibm.com/ai-agent-guide
信息内容: AI agents in 2026 require tool use, planning, memory and evaluation capabilities.
"""
    print(f"正在总结任务: {task.title}")
    summary = summarizer.summarize_task(state, task, context)
    print(f"总结长度: {len(summary)} 字符")
    print(f"总结预览:\n{summary[:300]}...")
    assert len(summary) > 10, "总结内容不应为空"
    print("✅ 步骤5 通过")


# ──────────────────────────────────────────────
# 步骤6：验证报告服务 services/reporter.py
# ──────────────────────────────────────────────
def test_step6_reporter():
    print("\n===== 步骤6: services/reporter.py =====")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from config import Configuration
    from models import SummaryState, TodoItem
    from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
    from prompts import report_writer_instructions
    from services.reporter import ReportingService

    config = Configuration.from_env()

    llm = HelloAgentsLLM(
        model=config.resolved_model(),
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        temperature=0.0,
    )
    report_agent = ToolAwareSimpleAgent(
        name="报告测试",
        llm=llm,
        system_prompt=report_writer_instructions.strip(),
        enable_tool_calling=False,
    )

    reporter = ReportingService(report_agent, config)

    # 构造含摘要的任务列表
    state = SummaryState(research_topic="AI Agent 学习路线")
    state.todo_items = [
        TodoItem(
            id=1, title="能力框架", intent="梳理核心能力", query="AI agent skills",
            status="completed", summary="## 任务总结\n- 工具调用是核心能力\n- 记忆模块提升长期任务能力",
            sources_summary="* IBM AI Guide : https://ibm.com",
        ),
        TodoItem(
            id=2, title="框架选型", intent="调研主流框架", query="AI agent framework",
            status="completed", summary="## 任务总结\n- LangGraph 适合复杂工作流\n- AutoGen 适合多 Agent 协作",
            sources_summary="* LangChain Docs : https://langchain.com",
        ),
    ]

    print(f"正在生成报告，主题：{state.research_topic}")
    report = reporter.generate_report(state)
    print(f"报告长度: {len(report)} 字符")
    print(f"报告预览:\n{report[:400]}...")
    assert len(report) > 50, "报告内容不应过短"
    print("✅ 步骤6 通过")


# ──────────────────────────────────────────────
# 步骤7：验证核心协调器 agent.py
# ──────────────────────────────────────────────
def test_step7_agent():
    print("\n===== 步骤7: agent.py =====")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    from agent import DeepResearchAgent

    agent = DeepResearchAgent()
    print(f"Agent 初始化成功，LLM 模型: {agent.llm.model}")
    print("正在执行研究（主题：Python asyncio 基础）...")

    result = agent.run("Python asyncio 基础")
    print(f"报告长度: {len(result.report_markdown or '')} 字符")
    print(f"任务数量: {len(result.todo_items)}")
    print(f"报告预览:\n{(result.report_markdown or '')[:400]}...")
    assert result.report_markdown, "报告不应为空"
    print("✅ 步骤7 通过")


# ──────────────────────────────────────────────
# 步骤8：验证 HTTP 接口 main.py
# ──────────────────────────────────────────────
def test_step8_api():
    print("\n===== 步骤8: main.py (HTTP 接口) =====")
    print("请先在另一个终端启动服务:")
    print("  cd Gdylagent_DR/backend && python src/main.py")
    print()
    print("然后用以下命令测试：")
    print()
    print("# 健康检查")
    print("  curl http://localhost:8000/healthz")
    print()
    print("# 同步研究接口")
    print('  curl -X POST http://localhost:8000/research \\')
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"topic": "Python asyncio 基础"}\'')
    print()
    print("# 流式研究接口（SSE）")
    print('  curl -X POST http://localhost:8000/research/stream \\')
    print('       -H "Content-Type: application/json" \\')
    print('       -d \'{"topic": "Python asyncio 基础"}\'')
    print()

    # 如果服务已运行，自动发送健康检查
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8000/healthz", timeout=2) as resp:
            print(f"服务已运行，健康检查响应: {resp.read().decode()}")
            print("✅ 步骤8 服务已就绪")
    except Exception:
        print("⚠️  服务未运行，请按上述方式手动启动后测试")


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────
STEPS = {
    1: test_step1_models,
    2: test_step2_config,
    3: test_step3_search,
    4: test_step4_planner,
    5: test_step5_summarizer,
    6: test_step6_reporter,
    7: test_step7_agent,
    8: test_step8_api,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="逐步验证各模块")
    parser.add_argument(
        "--step", type=int, choices=range(1, 9),
        help="只运行指定步骤（1-8），不指定则按顺序运行步骤1~3（不涉及LLM调用）"
    )
    args = parser.parse_args()

    if args.step:
        STEPS[args.step]()
    else:
        # 默认只跑不需要 LLM 的步骤
        print("提示：默认只运行步骤 1-3（无需 LLM）")
        print("      需要 LLM 的步骤请用 --step 参数单独运行，例如：python test_steps.py --step 4")
        for i in [1, 2, 3]:
            try:
                STEPS[i]()
            except Exception as e:
                print(f"❌ 步骤{i} 失败: {e}")
