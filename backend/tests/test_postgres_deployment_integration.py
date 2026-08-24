"""Deployment-shaped PostgreSQL, RLS, checkpoint, and S3 integration tests.

These tests are opt-in because the default test suite intentionally runs with
the deterministic local adapters. Set the three role URLs and the S3 settings
to exercise the production boundaries against disposable infrastructure.
"""

from __future__ import annotations

import os
from typing import cast
from uuid import uuid4

import pytest
from app.config import Settings
from app.db import build_session_factory, set_tenant_context
from app.models import Project
from app.object_store import build_object_store
from sqlalchemy import create_engine, text


def _required_postgres_urls() -> tuple[str, str, str]:
    values = (
        os.getenv("GROUNDLOOM_DATABASE_URL"),
        os.getenv("GROUNDLOOM_WORKER_DATABASE_URL"),
        os.getenv("GROUNDLOOM_MIGRATION_DATABASE_URL"),
    )
    if not all(values) or not all(value.startswith("postgres") for value in values if value):
        pytest.skip("Set the three PostgreSQL role URLs to run deployment integration tests")
    return cast(tuple[str, str, str], values)


def test_postgres_roles_enforce_rls_and_worker_bypass() -> None:
    api_url, worker_url, _migration_url = _required_postgres_urls()
    api_engine = create_engine(api_url)
    worker_engine = create_engine(worker_url)
    workspace_a = f"it-a-{uuid4().hex[:12]}"
    workspace_b = f"it-b-{uuid4().hex[:12]}"
    project_a = f"it-project-a-{uuid4().hex[:12]}"
    project_b = f"it-project-b-{uuid4().hex[:12]}"
    try:
        with worker_engine.begin() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == "groundloom_worker"
            for workspace_id in (workspace_a, workspace_b):
                connection.execute(
                    text(
                        "INSERT INTO workspaces (id, name, policy_json, created_at, updated_at) "
                        "VALUES (:id, :name, '{}'::jsonb, NOW(), NOW())"
                    ),
                    {"id": workspace_id, "name": workspace_id},
                )
            for project_id, workspace_id in ((project_a, workspace_a), (project_b, workspace_b)):
                connection.execute(
                    text(
                        "INSERT INTO projects "
                        "(workspace_id, id, name, project_type, brief, status, created_at, updated_at) "
                        "VALUES (:workspace_id, :id, :name, 'brief', 'integration', 'draft', NOW(), NOW())"
                    ),
                    {"workspace_id": workspace_id, "id": project_id, "name": project_id},
                )

        with api_engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == "groundloom_api"
            assert connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE oid = 'projects'::regclass"
                )
            ).one() == (True, True)

        session_factory = build_session_factory(api_url, api_engine)
        with session_factory() as session:
            set_tenant_context(session, workspace_a)
            visible = session.query(Project).filter(Project.id.in_([project_a, project_b])).all()
            assert [project.id for project in visible] == [project_a]

        with worker_engine.connect() as connection:
            count = connection.execute(
                text("SELECT COUNT(*) FROM projects WHERE id IN (:a, :b)"),
                {"a": project_a, "b": project_b},
            ).scalar_one()
            assert count == 2
    finally:
        with worker_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM projects WHERE id IN (:a, :b)"),
                {"a": project_a, "b": project_b},
            )
            connection.execute(
                text("DELETE FROM workspaces WHERE id IN (:a, :b)"),
                {"a": workspace_a, "b": workspace_b},
            )
        api_engine.dispose()
        worker_engine.dispose()


def test_postgres_checkpoint_schema_is_initialized_by_migrator() -> None:
    _api_url, _worker_url, migration_url = _required_postgres_urls()
    migration_engine = create_engine(migration_url)
    try:
        with migration_engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == "groundloom_migrator"
            tables = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                        "AND tablename IN ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes')"
                    )
                )
            }
            assert tables == {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}
    finally:
        migration_engine.dispose()


def test_s3_compatible_object_store_round_trip() -> None:
    _api_url, _worker_url, _migration_url = _required_postgres_urls()
    if os.getenv("GROUNDLOOM_OBJECT_STORE_BACKEND") != "s3":
        pytest.skip("Set GROUNDLOOM_OBJECT_STORE_BACKEND=s3 to run the object-store integration test")
    settings = Settings()
    store = build_object_store(settings)
    key = f"integration/{uuid4().hex}/artifact.txt"
    payload = b"groundloom deployment integration"
    store.put_bytes(key, payload)
    try:
        assert store.health()
        assert store.exists(key)
        assert store.get_bytes(key) == payload
    finally:
        store.delete_bytes(key)
        assert not store.exists(key)
