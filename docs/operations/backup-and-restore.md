# Backup and restore

Back up Postgres including checkpoints/audit/outbox and protect object storage versions according to retention. Encrypt, restrict access, monitor completion, and document RPO/RTO after phase-08 measurement.

Restore exercises use an isolated environment: restore DB, validate migrations/constraints/counts/sample hashes, restore/verify object references, rebuild derived indexes, resume eligible checkpoints, and execute core read/proposal/export smoke. Record duration, gaps, and corrective action. A backup without tested restore is not release evidence.

For the disposable SQLite local adapter, exercise the same copy/restore shape with:

```powershell
python backend/scripts/backup_local.py backup --database backend/data/groundloom.db --objects backend/data/objects --destination .local-backup
python backend/scripts/backup_local.py restore --database backend/data/restored.db --objects backend/data/restored-objects --destination .local-backup
```

Local backups include `manifest.json` with SHA-256 checksums for the database
and every object. Restore verifies the manifest before the command succeeds;
this is development evidence for integrity, not a substitute for an isolated
encrypted Postgres/object-store restore rehearsal.

The script is intentionally limited to local development. Production still requires encrypted Postgres/object-storage backups and an isolated restore rehearsal.
