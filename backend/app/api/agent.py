"""Agent API router — DB connections, image rules, schema inspection."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.db_connection import DbConnection
from app.models.user import User
from app.schemas.agent import (
    DbConnectionCreate,
    DbConnectionResponse,
    ImageRuleCreate,
    ImageRuleResponse,
    ImageRuleUpdate,
)
from app.services.auth_service import get_current_user
from app.services.database_service import (
    delete_db_connection,
    get_db_connection,
    list_db_connections,
    save_db_connection,
)
from app.services.rule_engine_service import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
)
from app.services.sql_agent_service import get_schema_summary

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# DB Connections
# ---------------------------------------------------------------------------

@router.post("/db-connections", response_model=DbConnectionResponse, status_code=201)
async def create_db_connection(
    body: DbConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DbConnectionResponse:
    conn = await save_db_connection(
        db,
        user_id=current_user.id,
        name=body.name,
        db_type=body.db_type,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=body.password,
        full_url=body.full_url,
    )
    return _conn_to_response(conn)


@router.get("/db-connections", response_model=list[DbConnectionResponse])
async def get_db_connections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DbConnectionResponse]:
    connections = await list_db_connections(db, current_user.id)
    return [_conn_to_response(c) for c in connections]


@router.delete("/db-connections/{connection_id}", status_code=204)
async def remove_db_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_db_connection(db, connection_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Connection not found"})


@router.get("/db-connections/{connection_id}/schema")
async def inspect_schema(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    conn = await get_db_connection(db, connection_id, current_user.id)
    if not conn:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Connection not found"})
    schema = await get_schema_summary(conn)
    return {"schema": schema}


@router.post("/threads/{thread_id}/set-db", response_model=dict)
async def set_thread_db(
    thread_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Attach a DB connection to a thread so NL queries are routed to it."""
    from app.services.thread_service import get_thread

    conn = await get_db_connection(db, connection_id, current_user.id)
    if not conn:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Connection not found"})

    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Thread not found"})

    context = thread.context or {}
    context["db_connection_id"] = str(connection_id)
    thread.context = context
    await db.commit()
    return {"db_connection_id": str(connection_id), "thread_id": str(thread_id)}


@router.delete("/threads/{thread_id}/set-db", status_code=204)
async def clear_thread_db(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove the DB connection from a thread."""
    from app.services.thread_service import get_thread

    thread = await get_thread(db, thread_id, current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Thread not found"})

    context = thread.context or {}
    context.pop("db_connection_id", None)
    thread.context = context
    await db.commit()


# ---------------------------------------------------------------------------
# Image rules
# ---------------------------------------------------------------------------

@router.post("/image-rules", response_model=ImageRuleResponse, status_code=201)
async def create_image_rule(
    body: ImageRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageRuleResponse:
    rule = await create_rule(
        db,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        rules=[r.model_dump() for r in body.rules],
    )
    return _rule_to_response(rule)


@router.get("/image-rules", response_model=list[ImageRuleResponse])
async def get_image_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ImageRuleResponse]:
    rules = await list_rules(db, current_user.id)
    return [_rule_to_response(r) for r in rules]


@router.patch("/image-rules/{rule_id}", response_model=ImageRuleResponse)
async def patch_image_rule(
    rule_id: uuid.UUID,
    body: ImageRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ImageRuleResponse:
    updated = await update_rule(
        db,
        rule_id,
        current_user.id,
        name=body.name,
        description=body.description,
        rules=[r.model_dump() for r in body.rules] if body.rules is not None else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Rule not found"})
    return _rule_to_response(updated)


@router.delete("/image-rules/{rule_id}", status_code=204)
async def delete_image_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_rule(db, rule_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Rule not found"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn_to_response(conn: DbConnection) -> DbConnectionResponse:
    return DbConnectionResponse(
        id=str(conn.id),
        name=conn.name,
        db_type=conn.db_type,
        host=conn.host,
        port=conn.port,
        database=conn.database,
        username=conn.username,
        created_at=conn.created_at.isoformat(),
    )


def _rule_to_response(rule) -> ImageRuleResponse:
    return ImageRuleResponse(
        id=str(rule.id),
        name=rule.name,
        description=rule.description,
        rules=rule.rules,
        created_at=rule.created_at.isoformat(),
    )
