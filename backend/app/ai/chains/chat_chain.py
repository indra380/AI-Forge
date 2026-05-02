from pathlib import Path

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable

from app.ai.llm import llm


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _load_prompt(file_name: str) -> str:
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8").strip()


def build_chat_chain() -> RunnableSerializable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _load_prompt("chat_system.txt")),
            ("human", _load_prompt("chat_human.txt")),
        ]
    )
    return prompt | llm | StrOutputParser()
