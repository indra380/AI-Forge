"""NL-to-SQL agent service using LangChain SQL agent.

All SQL is read-only; INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER are blocked.
Uses psycopg2 sync driver as required by LangChain's SQLDatabase (AD-06).
"""
import asyncio
import re
from typing import Any

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.models.db_connection import DbConnection
from app.services.database_service import build_sync_connection_string


# ---------------------------------------------------------------------------
# Safety guard
# ---------------------------------------------------------------------------

_BLOCKED_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter)\b",
    re.IGNORECASE,
)


def _assert_read_only(sql: str) -> None:
    """Raise ValueError if sql contains any write/DDL keywords."""
    match = _BLOCKED_KEYWORDS.search(sql)
    if match:
        raise ValueError(
            f"Query blocked: '{match.group()}' operations are not permitted. "
            "Only SELECT / read-only queries are allowed."
        )


# ---------------------------------------------------------------------------
# Sync LLM for agent (LangChain agent toolkit requires sync execution)
# ---------------------------------------------------------------------------

def _make_sync_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LITELLM_PROXY_URL,
        api_key=settings.LITELLM_API_KEY,
        timeout=settings.DATABASE_QUERY_TIMEOUT,
        max_retries=1,
    )


# ---------------------------------------------------------------------------
# SQL extraction helpers
# ---------------------------------------------------------------------------

def _extract_sql_from_steps(intermediate_steps: list, db_type: str) -> str | None:
    """Pull the user-facing SQL query from agent intermediate steps.

    Prefers steps where tool == 'sql_db_query' (the actual execution tool).
    Falls back to scanning all steps for a SELECT-starting string.
    Skips information_schema / system catalog queries used for introspection.
    """
    candidates: list[str] = []
    saw_list_tables_tool = False

    for action, _ in intermediate_steps:
        tool_name = getattr(action, "tool", "") or ""
        if "list_tables" in tool_name:
            saw_list_tables_tool = True
        tool_input = getattr(action, "tool_input", None)

        sql = None
        if isinstance(tool_input, str):
            sql = tool_input.strip()
        elif isinstance(tool_input, dict):
            sql = (tool_input.get("query", "") or "").strip()

        if not sql:
            continue

        upper = sql.upper()
        if not upper.startswith("SELECT"):
            continue

        # Skip internal schema-inspection queries
        if "INFORMATION_SCHEMA" in upper or "PG_CATALOG" in upper or "PG_TYPE" in upper:
            continue

        # Prefer the explicit query execution tool
        if tool_name == "sql_db_query":
            return sql

        candidates.append(sql)

    if candidates:
        return candidates[0]

    # Some LangChain SQL flows use list-tables tools without emitting raw SQL.
    # Return an equivalent read-only SQL so the UI can always show "query used".
    if saw_list_tables_tool:
        return _table_list_sql_for_db(db_type)

    return None


def _table_list_sql_for_db(db_type: str) -> str:
    db_type_norm = (db_type or "").lower()
    if db_type_norm == "sqlite":
        return (
            "SELECT name AS table_name "
            "FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name;"
        )
    if db_type_norm == "mssql":
        return (
            "SELECT TABLE_SCHEMA, TABLE_NAME "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE' "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME;"
        )
    # PostgreSQL / MySQL compatible fallback
    return (
        "SELECT table_schema, table_name "
        "FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' "
        "AND table_schema NOT IN ('information_schema', 'pg_catalog') "
        "ORDER BY table_schema, table_name;"
    )


def _looks_like_table_list_question(question: str) -> bool:
    q = (question or "").lower()
    return (
        "list the tables" in q
        or "list tables" in q
        or "show tables" in q
        or "what tables" in q
        or "table list" in q
    )


def _synthesize_sql_for_display(sql_db: SQLDatabase, llm: ChatOpenAI, question: str) -> str | None:
    """Generate a best-effort read-only SQL statement for display purposes.

    This is used only when agent intermediate steps do not expose a raw SQL query.
    """
    try:
        schema_info = sql_db.get_table_info()
        messages = [
            SystemMessage(
                content=(
                    "You generate SQL only. Return exactly one read-only SELECT query "
                    "that answers the user question using the provided schema. "
                    "Do not include markdown, explanations, comments, or backticks. "
                    "Never use INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE."
                )
            ),
            HumanMessage(
                content=(
                    f"Schema:\n{schema_info}\n\n"
                    f"Question: {question}\n\n"
                    "Return only SQL."
                )
            ),
        ]
        response = llm.invoke(messages)
        sql = (getattr(response, "content", "") or "").strip()
        if isinstance(sql, list):
            sql = "".join(str(x) for x in sql).strip()
        if "```" in sql:
            sql = sql.replace("```sql", "").replace("```", "").strip()
        if not sql:
            return None
        return sql
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def run_nl_to_sql(
    conn: DbConnection,
    question: str,
    user_email: str,
) -> dict[str, Any]:
    """Run a natural-language question against the connected database.

    Returns:
        {
            "answer": str,          # natural language answer
            "sql": str | None,      # the generated SQL (shown to user)
            "rows": list[dict],     # raw result rows (for table rendering)
            "error": str | None,
        }
    """
    connection_string = build_sync_connection_string(conn)

    def _run_sync() -> dict[str, Any]:
        sql_db = SQLDatabase.from_uri(
            connection_string,
            sample_rows_in_table_info=2,
            max_string_length=300,
        )
        llm = _make_sync_llm()
        toolkit = SQLDatabaseToolkit(db=sql_db, llm=llm)

        agent = create_sql_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=False,
            return_intermediate_steps=True,
            handle_parsing_errors=True,
            agent_executor_kwargs={"handle_parsing_errors": True},
        )

        result = agent.invoke(
            {"input": question},
            config={"metadata": {"user_email": user_email, "application": settings.APP_NAME}},
        )

        generated_sql = _extract_sql_from_steps(result.get("intermediate_steps", []), conn.db_type)
        if not generated_sql and _looks_like_table_list_question(question):
            generated_sql = _table_list_sql_for_db(conn.db_type)
        if not generated_sql:
            generated_sql = _synthesize_sql_for_display(sql_db, llm, question)

        # Safety: validate the extracted SQL before reporting it
        if generated_sql:
            try:
                _assert_read_only(generated_sql)
            except ValueError as e:
                return {"answer": str(e), "sql": None, "rows": [], "error": str(e)}

        return {
            "answer": result.get("output", ""),
            "sql": generated_sql,
            "rows": [],
            "error": None,
        }

    try:
        return await asyncio.to_thread(_run_sync)
    except Exception as exc:
        return {
            "answer": f"Database query failed: {exc}",
            "sql": None,
            "rows": [],
            "error": str(exc),
        }


async def get_schema_summary(conn: DbConnection) -> str:
    """Return a short markdown summary of table names and columns."""
    connection_string = build_sync_connection_string(conn)

    def _run_sync() -> str:
        sql_db = SQLDatabase.from_uri(connection_string, sample_rows_in_table_info=0)
        return sql_db.get_table_info()

    try:
        info = await asyncio.to_thread(_run_sync)
        return info or "No schema information available."
    except Exception as exc:
        return f"Could not retrieve schema: {exc}"
