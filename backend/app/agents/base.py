"""
Agent 抽象基类 — 基于 LangGraph StateGraph 模式。

每个 Agent 有明确的 Input/Output Pydantic schema，
通过 build_prompt() 构建 system+user prompt，
通过 run() 执行 LLM 调用并返回结构化输出。

设计原则:
- Agent 独立可测 — 每个 Agent 可单独单元测试
- 结构化接口 — 输入/输出均为 Pydantic 模型
- 链路可追溯 — 每次执行记录到数据库
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


class BaseAgent(ABC, Generic[I, O]):
    """所有 Agent 的抽象基类"""

    name: str = "base"
    description: str = ""

    @abstractmethod
    async def run(self, input_data: I, context: dict | None = None) -> O:
        """执行 Agent，输入输出均为结构化 Pydantic 模型"""

    @abstractmethod
    def build_prompt(self, input_data: I, context: dict | None = None) -> tuple[str, str]:
        """构建 (system_prompt, user_prompt)"""

    async def _call_llm(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """调用 LLM 获取响应。kwargs 传递给 provider (如 max_tokens, temperature)"""
        from backend.app.core.llm_provider import get_llm

        llm = get_llm()
        try:
            response = await llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], **kwargs)
            return response.content
        finally:
            await llm.close()

    async def _call_llm_stream(self, system_prompt: str, user_prompt: str, **kwargs):
        """流式调用 LLM，逐 token yield。"""
        from backend.app.core.llm_provider import get_llm

        llm = get_llm()
        async for token in llm.chat_stream([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], **kwargs):
            yield token

    @staticmethod
    def _parse_llm_json(text: str) -> dict:
        """从 LLM 输出中解析 JSON。处理 markdown 包裹、截断、未转义换行等常见问题。"""
        import json
        t = text.strip()
        # 去除 markdown 代码块
        if t.startswith("```"):
            end = t.find("\n", 3)
            t = t[end + 1:] if end > 0 else t[3:]
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
        # 找最外层 JSON
        start = t.find("{")
        end = t.rfind("}") + 1
        if start < 0 or end <= start:
            return {}
        try:
            return json.loads(t[start:end])
        except json.JSONDecodeError:
            # 尝试修复常见问题：缺失结尾的 }
            # 补上可能缺失的引号和括号
            for repair in ["}", '"}', '"}]"}', "}]}"]:
                try:
                    return json.loads(t[start:end] + repair)
                except json.JSONDecodeError:
                    continue
            return {}

    async def log_execution(self, task_id: str, input_data: I, output_data: O, tokens: int, duration_ms: int):
        """记录执行日志到数据库。DB 不可用时静默跳过。"""
        try:
            from backend.app.core.db import async_session
            from backend.app.models import AgentExecution

            async with async_session() as session:
                exec_record = AgentExecution(
                    task_id=task_id,
                    agent_name=self.name,
                    input_summary=str(input_data)[:200],
                    output=output_data.model_dump(),
                    tokens_used=tokens,
                    duration_ms=duration_ms,
                )
                session.add(exec_record)
                await session.commit()
        except Exception:
            pass  # 开发阶段 DB 未就绪时静默跳过
