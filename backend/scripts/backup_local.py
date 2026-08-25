"""Create or restore a disposable local SQLite/object-store backup."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def copy_tree(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(database: Path, objects: Path) -> dict[str, object]:
    files = {
        str(path.relative_to(objects)).replace("\\", "/"): sha256_file(path)
        for path in sorted(objects.rglob("*"))
        if path.is_file()
    }
    return {"database_sha256": sha256_file(database), "objects": files}


def verify_manifest(database: Path, objects: Path, manifest: dict[str, object]) -> None:
    if sha256_file(database) != manifest.get("database_sha256"):
        raise SystemExit("Backup verification failed: database checksum mismatch")
    expected = manifest.get("objects", {})
    if not isinstance(expected, dict):
        raise SystemExit("Backup verification failed: invalid object manifest")
    actual = {
        str(path.relative_to(objects)).replace("\\", "/")
        for path in objects.rglob("*")
        if path.is_file()
    }
    if actual != set(str(relative) for relative in expected):
        raise SystemExit("Backup verification failed: object inventory mismatch")
    for relative, digest in expected.items():
        target = objects / str(relative)
        if not target.is_file() or sha256_file(target) != digest:
            raise SystemExit(f"Backup verification failed: object checksum mismatch: {relative}")


def create_backup(database: Path, objects: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    db_target = destination / "groundloom.db"
    objects_target = destination / "objects"
    shutil.copy2(database, db_target)
    copy_tree(objects, objects_target)
    (destination / "manifest.json").write_text(
        json.dumps(build_manifest(db_target, objects_target), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def restore_backup(database: Path, objects: Path, destination: Path) -> None:
    db_source = destination / "groundloom.db"
    objects_source = destination / "objects"
    manifest_path = destination / "manifest.json"
    if not db_source.exists():
        raise SystemExit(f"Backup database not found: {db_source}")
    if not manifest_path.exists():
        raise SystemExit(f"Backup manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Validate the backup before touching the restore target. A failed restore
    # must not replace a usable target with a corrupt or incomplete copy.
    verify_manifest(db_source, objects_source, manifest)
    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_source, database)
    copy_tree(objects_source, objects)
    verify_manifest(database, objects, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "restore"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--objects", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "backup":
        create_backup(args.database, args.objects, args.destination)
        return
    restore_backup(args.database, args.objects, args.destination)


if __name__ == "__main__":
    main()
