from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(database_url: str):
    return sessionmaker(
        bind=make_engine(database_url), autoflush=False, autocommit=False, expire_on_commit=False
    )


def init_database(database_url: str) -> None:
    if database_url.startswith("sqlite"):
        path = database_url.removeprefix("sqlite:///")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    from . import models  # noqa: F401

    engine = make_engine(database_url)
    Base.metadata.create_all(engine)


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
