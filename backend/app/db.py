from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import Settings


class Base(DeclarativeBase):
    pass


def set_tenant_context(session: Session, workspace_id: str) -> None:
    """Bind the trusted workspace to this session and its current transaction.

    PostgreSQL RLS policies read ``app.workspace_id`` with ``current_setting``.
    The setting is transaction-local, so the session event below reapplies it
    whenever SQLAlchemy starts a new transaction after an application commit.
    SQLite keeps the trusted value in ``Session.info`` but does not execute the
    PostgreSQL-only statement.
    """
    session.info["workspace_id"] = workspace_id
    if session.get_bind().dialect.name == "postgresql" and session.in_transaction():
        session.execute(
            text("SELECT set_config('app.workspace_id', :workspace_id, true)"),
            {"workspace_id": workspace_id},
        )


def set_worker_context(session: Session) -> None:
    """Mark a trusted leased-worker session for cross-workspace queue claims."""
    session.info.pop("workspace_id", None)
    session.info["service_role"] = "worker"
    if session.get_bind().dialect.name == "postgresql" and session.in_transaction():
        session.execute(
            text("SELECT set_config('app.service_role', 'worker', true)")
        )


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, _transaction, connection) -> None:
    workspace_id = session.info.get("workspace_id")
    service_role = session.info.get("service_role")
    if workspace_id and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.workspace_id', :workspace_id, true)"),
            {"workspace_id": workspace_id},
        )
    if service_role and connection.dialect.name == "postgresql":
        connection.execute(
            text("SELECT set_config('app.service_role', :service_role, true)"),
            {"service_role": service_role},
        )


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    pool_options = {}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        pool_options["poolclass"] = StaticPool
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True, **pool_options)


def build_session_factory(database_url: str, engine=None):
    return sessionmaker(
        bind=engine or make_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def init_database(database_url: str):
    if database_url.startswith("sqlite"):
        path = database_url.removeprefix("sqlite:///")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    from . import models  # noqa: F401

    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def prepare_worker_database(settings: Settings):
    """Build a worker session factory without production DDL or migrations.

    Local SQLite workers bootstrap their disposable database for convenience.
    Staging and production workers connect through the dedicated worker role;
    schema changes are applied by the migration process, never by a worker.
    """
    worker_url = settings.worker_database_url or settings.database_url
    if worker_url.startswith("sqlite"):
        from .migrations import apply_migrations

        apply_migrations(worker_url)
        engine = init_database(worker_url)
    else:
        engine = make_engine(worker_url)
    return worker_url, engine, build_session_factory(worker_url, engine)


def session_scope(factory) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
