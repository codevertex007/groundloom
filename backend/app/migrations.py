from datetime import UTC, datetime

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .db import Base, make_engine

MIGRATION_ID = "001_initial_domain_schema"
ADAPTERS_MIGRATION_ID = "002_ingestion_jobs_and_provider_adapters"
RETENTION_EXPORT_MIGRATION_ID = "003_retention_deletion_and_export_leases"
INDEX_REBUILD_MIGRATION_ID = "004_index_rebuild_jobs"
DELEGATED_WORKER_MIGRATION_ID = "005_delegated_task_leases"
APPROVAL_USAGE_MIGRATION_ID = "006_approval_and_run_usage"
WORKSPACE_PREFERENCES_MIGRATION_ID = "007_workspace_preferences"
AGENT_RUN_WORKER_MIGRATION_ID = "008_agent_run_workers"
WORKER_HEARTBEAT_MIGRATION_ID = "009_worker_heartbeats"
BUDGET_CONTROLS_MIGRATION_ID = "010_budget_controls"
POSTGRES_RLS_MIGRATION_ID = "011_postgres_rls_tenant_isolation"
ACTIVE_AGENT_TURN_MIGRATION_ID = "012_active_agent_turn_uniqueness"
WORKER_ROLE_RLS_MIGRATION_ID = "013_worker_role_rls_boundary"

_RLS_WORKSPACE_TABLES = (
    "workspace_preferences",
    "projects",
    "project_config_versions",
    "sources",
    "source_versions",
    "ingestion_jobs",
    "index_rebuild_jobs",
    "source_blocks",
    "source_chunks",
    "skills",
    "skill_versions",
    "agent_threads",
    "agent_runs",
    "approval_requests",
    "public_events",
    "todos",
    "outline_versions",
    "content_versions",
    "content_blocks",
    "patches",
    "validation_runs",
    "validation_findings",
    "export_jobs",
    "retention_policies",
    "deletion_requests",
    "idempotency_records",
    "memory_items",
    "delegated_tasks",
)


def _apply_postgres_rls(connection) -> None:
    """Install defense-in-depth policies for every workspace-scoped table."""
    for table in _RLS_WORKSPACE_TABLES:
        connection.exec_driver_sql(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        connection.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        connection.exec_driver_sql(
            f"DROP POLICY IF EXISTS groundloom_workspace_isolation ON {table}"
        )
        predicate = (
            "workspace_id IS NULL OR workspace_id = current_setting('app.workspace_id', true)"
            if table in {"skills", "skill_versions"}
            else "workspace_id = current_setting('app.workspace_id', true)"
        )
        connection.exec_driver_sql(
            f"CREATE POLICY groundloom_workspace_isolation ON {table} "
            f"USING ((current_user = 'groundloom_worker') OR ({predicate})) "
            f"WITH CHECK ((current_user = 'groundloom_worker') OR ({predicate}))"
        )


def apply_migrations(database_url: str) -> None:
    from . import models  # noqa: F401

    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations (id VARCHAR(160) PRIMARY KEY, applied_at VARCHAR(64) NOT NULL)"
            )
        )
        migration_ids: list[str] = [
            MIGRATION_ID,
            ADAPTERS_MIGRATION_ID,
            RETENTION_EXPORT_MIGRATION_ID,
            INDEX_REBUILD_MIGRATION_ID,
            DELEGATED_WORKER_MIGRATION_ID,
            APPROVAL_USAGE_MIGRATION_ID,
            WORKSPACE_PREFERENCES_MIGRATION_ID,
            AGENT_RUN_WORKER_MIGRATION_ID,
            WORKER_HEARTBEAT_MIGRATION_ID,
            BUDGET_CONTROLS_MIGRATION_ID,
            POSTGRES_RLS_MIGRATION_ID,
            ACTIVE_AGENT_TURN_MIGRATION_ID,
            WORKER_ROLE_RLS_MIGRATION_ID,
        ]
        preference_columns = {
            column["name"] for column in inspect(engine).get_columns("workspace_preferences")
        }
        for name, sql_type, default in (
            ("daily_token_budget", "INTEGER", "100000"),
            ("daily_cost_budget_usd", "FLOAT", "25.0"),
        ):
            if name not in preference_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE workspace_preferences ADD COLUMN {name} {sql_type} DEFAULT {default}"
                    )
                )
        # create_all creates new tables but does not add columns to a prior
        # release. These additive columns are the only compatibility change in
        # this migration and are safe before the worker is upgraded.
        existing_export_columns = {
            column["name"] for column in inspect(engine).get_columns("export_jobs")
        }
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
        for name, sql_type, default in (
            ("attempts", "INTEGER", "0"),
            ("lease_owner", "VARCHAR(120)", "NULL"),
            ("lease_until", timestamp_type, "NULL"),
        ):
            if name not in existing_export_columns:
                connection.execute(
                    text(f"ALTER TABLE export_jobs ADD COLUMN {name} {sql_type} DEFAULT {default}")
                )
        delegated_columns = {
            column["name"] for column in inspect(engine).get_columns("delegated_tasks")
        }
        for name, sql_type, default in (
            ("lease_owner", "VARCHAR(120)", "NULL"),
            ("lease_until", timestamp_type, "NULL"),
        ):
            if name not in delegated_columns:
                connection.execute(
                    text(f"ALTER TABLE delegated_tasks ADD COLUMN {name} {sql_type} DEFAULT {default}")
                )
        run_columns = {column["name"] for column in inspect(engine).get_columns("agent_runs")}
        for name in ("usage_json", "budget_json"):
            if name not in run_columns:
                connection.execute(
                    text(f"ALTER TABLE agent_runs ADD COLUMN {name} JSON DEFAULT '{{}}'")
                )
        for name, sql_type, default in (
            ("attempts", "INTEGER", "0"),
            ("lease_owner", "VARCHAR(120)", "NULL"),
            ("lease_until", timestamp_type, "NULL"),
        ):
            if name not in run_columns:
                connection.execute(
                    text(f"ALTER TABLE agent_runs ADD COLUMN {name} {sql_type} DEFAULT {default}")
                )
        for migration_id in migration_ids:
            if database_url.startswith("sqlite"):
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (:id, :at)"
                    ),
                    {"id": migration_id, "at": datetime.now(UTC).isoformat()},
                )
            else:
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations (id, applied_at) VALUES (:id, :at) ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": migration_id, "at": datetime.now(UTC).isoformat()},
                )
        if engine.dialect.name == "postgresql":
            _apply_postgres_rls(connection)
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_runs_one_active_per_project "
                "ON agent_runs (project_id) "
                "WHERE status IN ('queued', 'running', 'waiting_for_user', 'waiting_for_approval')"
            )
        )
    engine.dispose(close=True)


def migration_status(db: Session) -> list[str]:
    rows = db.execute(text("SELECT id FROM schema_migrations ORDER BY id")).all()
    return [row[0] for row in rows]
