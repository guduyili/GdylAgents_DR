"""Service responsible for converting the research topic into actionable tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from prompts import get_current_date, todo_planner_instructions
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)

TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)

class PlanningService:
    """Wraps the planner agent to produce structured TODO items."""

    def __init__(self, planner_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = planner_agent
        self._config = config

    def plan_todo_list(self, state: SummaryState) -> List[TodoItem]:
        """Ask the planner agent to break the topic into actionable tasks."""

        prompt = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=state.research_topic,
        )

        response = self._agent.run(prompt)
        self._agent.clear_history()

        logger.info("Planner raw output (truncated): %s", response[:500])

        tasks_payload = self._extract_tasks(response)
        todo_items: List[TodoItem] = []

        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip()

            if not query:
                query = state.research_topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query,
            )
            todo_items.append(task)

        state.todo_items = todo_items

        titles = [task.title for task in todo_items]
        logger.info("Planner produced %d tasks: %s", len(todo_items), titles)
        return todo_items

    @staticmethod
    def create_fallback_task(state: SummaryState) -> TodoItem:
        """Create a minimal fallback task when planning failed."""

        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展" if state.research_topic else "基础背景梳理",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        """Parse planner output into a list of task dictionaries.

        Parsing priority:
        1. Valid JSON payload (dict with "tasks" key, or list of dicts)
        2. TOOL_CALL expression containing a "tasks" key
        3. Markdown table -- rows map to tasks (column headers become keys)
        4. Numbered list -- each line becomes a task with title only
        """
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        # --- Priority 1: JSON payload ---
        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        if tasks:
            logger.debug("Planner tasks extracted from JSON payload (%d tasks)", len(tasks))
            return tasks

        # --- Priority 2: TOOL_CALL expression ---
        tool_payload = self._extract_tool_payload(text)
        if tool_payload and isinstance(tool_payload.get("tasks"), list):
            for item in tool_payload["tasks"]:
                if isinstance(item, dict):
                    tasks.append(item)

        if tasks:
            logger.debug("Planner tasks extracted from TOOL_CALL (%d tasks)", len(tasks))
            return tasks

        # --- Priority 3: Markdown table ---
        table_tasks = self._extract_markdown_table_tasks(text)
        if table_tasks:
            logger.debug("Planner tasks extracted from Markdown table (%d tasks)", len(table_tasks))
            return table_tasks

        # --- Priority 4: Numbered list ---
        list_tasks = self._extract_numbered_list_tasks(text)
        if list_tasks:
            logger.debug("Planner tasks extracted from numbered list (%d tasks)", len(list_tasks))
            return list_tasks

        logger.warning("Planner output could not be parsed into any task format")
        return tasks

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        """Try to locate and parse a JSON object or array from the text."""

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None

    def _extract_tool_payload(self, text: str) -> Optional[dict[str, Any]]:
        """Parse the first TOOL_CALL expression in the output."""

        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        body = match.group("body")

        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        parts = [segment.strip() for segment in body.split(",") if segment.strip()]
        payload: dict[str, Any] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            payload[key.strip()] = value.strip().strip('"').strip("'")

        return payload or None

    @staticmethod
    def _extract_markdown_table_tasks(text: str) -> List[dict[str, Any]]:
        """Extract tasks from a Markdown table.

        Supports tables like:
        | 序号 | 名称 | 意图 | 查询 |
        |------|------|------|------|
        | 1 | 任务1 | 描述1 | query1 |
        """
        # Match table rows: lines starting with |
        table_lines = [line.strip() for line in text.split("\n") if line.strip().startswith("|")]
        if len(table_lines) < 3:  # Need header, separator, and at least 1 data row
            return []

        # Parse header
        header_cells = [c.strip() for c in table_lines[0].split("|") if c.strip()]
        # Skip separator row (contains ---)
        data_lines = [line for line in table_lines[1:] if "---" not in line]

        # Map common column names to canonical keys
        # Covers Chinese headers that Flash models might produce
        key_map = {
            "title": "title", "\u4efb\u52a1\u540d\u79f0": "title", "\u540d\u79f0": "title",
            "\u4efb\u52a1": "title", "\u6807\u9898": "title",
            "\u7535\u5f71": "title", "\u7535\u5f71\uff08\u5e74\u4efd\uff09": "title",
            "\u63a8\u8350\u7535\u5f71": "title",
            "intent": "intent", "\u610f\u56fe": "intent", "\u76ee\u7684": "intent",
            "\u63a8\u8350\u7406\u7531": "intent", "\u63a8\u8350\u7406\u7531\uff08\u7b80\u8981\uff09": "intent",
            "\u7b80\u8981": "intent", "\u63cf\u8ff0": "intent",
            "query": "query", "\u67e5\u8be2": "query", "\u68c0\u7d22\u5173\u952e\u8bcd": "query",
            "\u5173\u952e\u8bcd": "query", "\u68c0\u7d22\u8bcd": "query",
            "\u5e8f\u53f7": "id", "\u7f16\u53f7": "id", "\u53f7": "id", "\u5b50\u7c7b\u578b": "intent",
            "\u5730\u57df": "intent",
        }

        tasks: List[dict[str, Any]] = []
        for line in data_lines:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if not cells:
                continue

            task: dict[str, Any] = {}
            for i, cell in enumerate(cells):
                if i < len(header_cells):
                    header = header_cells[i].lower()
                    canonical = key_map.get(header, header)
                    task[canonical] = cell

            if task:
                # Ensure minimum required keys: pick best column as title
                if "title" not in task:
                    # Use the first non-numeric, non-id column value as title
                    title_found = False
                    for key, val in task.items():
                        if key in ("id",) or val.strip().isdigit():
                            continue
                        task["title"] = val
                        title_found = True
                        break
                    if not title_found and task:
                        task["title"] = list(task.values())[0]
                tasks.append(task)

        return tasks if len(tasks) >= 2 else []

    @staticmethod
    def _extract_numbered_list_tasks(text: str) -> List[dict[str, Any]]:
        """Extract tasks from a numbered or bulleted list.

        Supports formats like:
        1. 任务名称 - 任务描述
        - 任务名称：任务描述
        """
        # Match lines like: "1. xxx" or "1) xxx" or "- xxx" or "* xxx"
        pattern = re.compile(r"^(?:\d+[.)\]\s]+|[\-*])\s*(.+)$", re.MULTILINE)
        matches = pattern.findall(text)

        if len(matches) < 2:
            return []

        tasks: List[dict[str, Any]] = []
        for line in matches:
            line = line.strip()
            if not line or len(line) < 2:
                continue

            # Try to split on common delimiters:  - , : , ：, —
            parts = re.split(r"\s*[\-\u2014\u2013\u2015:]\s+", line, maxsplit=1)
            if len(parts) >= 2:
                title = parts[0].strip()
                intent = parts[1].strip()
            else:
                title = line
                intent = "聚焦主题的关键问题"

            tasks.append({"title": title, "intent": intent, "query": title})

        return tasks if len(tasks) >= 2 else []
