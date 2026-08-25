# Backup and restore

Back up Postgres including checkpoints/audit/outbox and protect object storage versions according to retention. Encrypt database backups through the deployment backup/KMS control plane; object-store writes use the configured AES-256 or KMS server-side encryption policy in production. Restrict access, monitor completion, and document RPO/RTO after phase-08 measurement.

Restore exercises use an isolated environment: restore DB, validate migrations/constraints/counts/sample hashes, restore/verify object references, rebuild derived indexes, resume eligible checkpoints, and execute core read/proposal/export smoke. Record duration, gaps, and corrective action. A backup without tested restore is not release evidence.

For the disposable SQLite local adapter, exercise the same copy/restore shape with:

```powershell
python backend/scripts/backup_local.py backup --database backend/data/groundloom.db --objects backend/data/objects --destination .local-backup
python backend/scripts/backup_local.py restore --database backend/data/restored.db --objects backend/data/restored-objects --destination .local-backup
```

Local backups include `manifest.json` with SHA-256 checksums for the database
and every object. Restore validates the source database, exact object inventory,
and every checksum before replacing the target, then verifies the restored copy
again. A failed validation leaves the existing restore target untouched. This
is development evidence for integrity, not a substitute for an isolated
encrypted Postgres/object-store restore rehearsal.

The script is intentionally limited to local development. Production still requires encrypted Postgres/object-storage backups and an isolated restore rehearsal.
