"""General-purpose LangChain ReAct agent with tools.

Tools:
  - calculator     : safe math evaluation
  - datetime_info  : return current date/time
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _safe_calculator(expression: str) -> str:
    """Evaluate a simple mathematical expression safely."""
    import ast
    import math
    import operator as op

    allowed_nodes = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.Pow: op.pow,
        ast.USub: op.neg,
        ast.Mod: op.mod,
    }
    allowed_names = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed_names["abs"] = abs
    allowed_names["round"] = round

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.BinOp):
            return allowed_nodes[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            return allowed_nodes[type(node.op)](_eval(node.operand))
        if isinstance(node, ast.Name) and node.id in allowed_names:
            return float(allowed_names[node.id])
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in allowed_names:
                args = [_eval(a) for a in node.args]
                return float(allowed_names[node.func.id](*args))
        raise ValueError(f"Unsupported expression: {type(node).__name__}")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval(tree.body)
        return str(result)
    except Exception as exc:
        return f"Error evaluating expression: {exc}"


def _datetime_info(_: str = "") -> str:
    """Return current UTC date and time."""
    now = datetime.now(timezone.utc)
    return now.strftime("Current UTC date/time: %Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# Agent prompt
# ---------------------------------------------------------------------------

_REACT_PROMPT_TEMPLATE = """You are a helpful AI assistant with access to tools. Use tools to complete tasks accurately.

You have access to the following tools:

{tools}

Use the following format EXACTLY:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Chat History:
{chat_history}

Question: {input}
Thought:{agent_scratchpad}"""

_REACT_PROMPT = PromptTemplate.from_template(_REACT_PROMPT_TEMPLATE)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def _build_tools() -> list[Tool]:
    return [
        Tool(
            name="calculator",
            func=_safe_calculator,
            description=(
                "Evaluate mathematical expressions. "
                "Input should be a valid math expression like '2 + 2' or 'sqrt(144)'."
            ),
        ),
        Tool(
            name="datetime_info",
            func=_datetime_info,
            description="Get the current UTC date and time. Input can be anything.",
        ),
    ]


def _build_agent_executor() -> AgentExecutor:
    tools = _build_tools()
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_API_KEY,
        timeout=60,
        max_retries=1,
    )
    agent = create_react_agent(llm=llm, tools=tools, prompt=_REACT_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
        max_iterations=8,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

async def run_agent(
    task: str,
    user_email: str,
    chat_history: str = "",
) -> dict[str, Any]:
    """Run the ReAct agent on a task.

    Returns:
        {"answer": str, "steps": list[str], "error": str | None}
    """
    def _run_sync() -> dict[str, Any]:
        executor = _build_agent_executor()
        result = executor.invoke(
            {"input": task, "chat_history": chat_history},
            config={"metadata": {"user_email": user_email, "application": settings.APP_NAME}},
        )
        steps: list[str] = []
        for action, observation in result.get("intermediate_steps", []):
            tool_name = getattr(action, "tool", "tool")
            tool_input = getattr(action, "tool_input", "")
            steps.append(f"**Tool:** `{tool_name}` — Input: `{tool_input}`\n**Result:** {observation}")

        return {
            "answer": result.get("output", ""),
            "steps": steps,
            "error": None,
        }

    try:
        return await asyncio.to_thread(_run_sync)
    except Exception as exc:
        return {
            "answer": f"Agent execution failed: {exc}",
            "steps": [],
            "error": str(exc),
        }
