"""
Backup Utility for GameStringer CLI.

Ensures game files are safely backed up before any repatching operation is executed.
"""

import os
import shutil
import datetime
from typing import List, Optional


def create_backup(target_path: str, backup_dir: Optional[str] = None) -> str:
    """
    Create a timestamped backup copy of a target file or directory.

    :param target_path: Absolute or relative path to file or directory to back up
    :param backup_dir: Optional directory to store backup (defaults to alongside original)
    :return: Path to the created backup file/directory
    """
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Target path for backup does not exist: {target_path}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(target_path.rstrip("/\\"))

    if backup_dir:
        os.makedirs(backup_dir, exist_ok=True)
        backup_path = os.path.join(backup_dir, f"{base_name}.bak_{timestamp}")
    else:
        backup_path = f"{target_path}.bak_{timestamp}"

    if os.path.isdir(target_path):
        shutil.copytree(target_path, backup_path)
    else:
        shutil.copy2(target_path, backup_path)

    return backup_path


def restore_backup(backup_path: str, target_path: str) -> bool:
    """
    Restore a file or directory from its backup copy.

    :param backup_path: Path to backup file/directory
    :param target_path: Path to target file/directory to overwrite
    :return: True if successfully restored
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    if os.path.exists(target_path):
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)

    if os.path.isdir(backup_path):
        shutil.copytree(backup_path, target_path)
    else:
        shutil.copy2(backup_path, target_path)

    return True


def list_backups(target_path: str) -> List[str]:
    """
    List all backup files associated with a given target path.

    :param target_path: Base target path
    :return: List of backup file paths sorted by newest first
    """
    parent_dir = os.path.dirname(os.path.abspath(target_path))
    base_name = os.path.basename(target_path.rstrip("/\\"))

    if not os.path.exists(parent_dir):
        return []

    backups = []
    prefix = f"{base_name}.bak_"
    for entry in os.listdir(parent_dir):
        if entry.startswith(prefix) or entry == f"{base_name}.bak":
            backups.append(os.path.join(parent_dir, entry))

    backups.sort(reverse=True)
    return backups
