-- Disposable local roles for deployment-shaped Groundloom testing.
-- These credentials are local-only examples and must never be reused.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundloom_api') THEN
        CREATE ROLE groundloom_api LOGIN PASSWORD 'groundloom-api-local-only'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundloom_worker') THEN
        CREATE ROLE groundloom_worker LOGIN PASSWORD 'groundloom-worker-local-only'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'groundloom_migrator') THEN
        CREATE ROLE groundloom_migrator LOGIN PASSWORD 'groundloom-migrator-local-only'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE groundloom TO groundloom_api, groundloom_worker, groundloom_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO groundloom_migrator;
GRANT USAGE ON SCHEMA public TO groundloom_api, groundloom_worker;

-- Domain tables are created and migrated by the migrator. Runtime roles only
-- receive DML privileges; forced RLS supplies the tenant boundary.
ALTER DEFAULT PRIVILEGES FOR ROLE groundloom_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO groundloom_api, groundloom_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE groundloom_migrator IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO groundloom_api, groundloom_worker;
