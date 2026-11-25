"""GET /api/health (SPEC_V4 §12.3): what the uptime check, Docker's health check and the deploy
script call. 200 only when the database answers and its migrations are at the code's head; 503
with what's wrong otherwise. No secrets, no player data."""

import logging
from functools import cache
from typing import Literal

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import Engine, text

from app.db.migrate import alembic_config

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


class Health(BaseModel):
    ok: bool
    database: Literal["ok", "unreachable"]
    migrations: Literal["ok", "behind", "unknown"]


@cache
def code_head() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def check(engine: Engine) -> Health:
    try:
        with engine.connect() as connection:
            # Read directly: Alembic's MigrationContext would log two lines per check.
            current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as error:  # any database failure means unhealthy; say so, not why
        logger.error("health check: database unreachable (%s)", type(error).__name__)
        return Health(ok=False, database="unreachable", migrations="unknown")
    if current != code_head():
        logger.error("health check: migrations at %s, code expects %s", current, code_head())
        return Health(ok=False, database="ok", migrations="behind")
    return Health(ok=True, database="ok", migrations="ok")


@router.get("/api/health")
def health(request: Request, response: Response) -> Health:
    result = check(request.app.state.engine)
    if not result.ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
