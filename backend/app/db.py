from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


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
