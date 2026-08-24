"""Create or restore a disposable local SQLite/object-store backup."""

import argparse
import shutil
from pathlib import Path


def copy_tree(source: Path, target: Path) -> None:
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "restore"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--objects", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    db_target = args.destination / "groundloom.db"
    objects_target = args.destination / "objects"
    if args.command == "backup":
        args.destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.database, db_target)
        copy_tree(args.objects, objects_target)
        return
    if not db_target.exists():
        raise SystemExit(f"Backup database not found: {db_target}")
    args.database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_target, args.database)
    copy_tree(objects_target, args.objects)


if __name__ == "__main__":
    main()
