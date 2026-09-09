"""Pre-run hardening: TM snapshot and orphaned agy-artifact sweep.

Both are called from cli.py's cmd_run before pipeline.run() starts --
neither belongs in pipeline.py itself, which stays free of any
assumption about the antigravity_cli provider's on-disk session layout
or the local filesystem's temp directory.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


def snapshot_tm(config) -> Path:
    """Copy the project's TM sqlite file to a timestamped backup before a
    real (non-dry-run) run starts. checkpoint.py already refuses to
    silently reset a corrupted checkpoint.json -- nothing previously
    protected the TM database itself the same way against a mid-write
    crash (disk full, kill -9). Cheap: a single file, not a project
    directory copy.

    Returns the TM db path unchanged (no-op) if it doesn't exist yet
    (first run for this project -- nothing to snapshot).
    """
    tm_path = Path(config.tm_db_path)
    if not tm_path.exists():
        return tm_path

    backups_dir = tm_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup_path = backups_dir / f"{tm_path.stem}.{stamp}.bak{tm_path.suffix}"
    shutil.copy2(tm_path, backup_path)
    logger.info("TM snapshot written to %s", backup_path)
    return backup_path


def sweep_orphaned_agy_artifacts(max_age_s: int = 3600) -> Dict[str, int]:
    """Removes stray temp-prompt files and antigravity-cli brain session
    directories left behind by a crashed (kill -9, OOM, power loss) prior
    run -- a clean run already removes both itself (see
    antigravity_cli_provider.py's _run_agy `finally` block and
    _cleanup_antigravity_session), so anything found here by definition
    survived an unclean exit.

    Only removes locpipe's own temp files -- matched by the
    'locpipe_agy_prompt_' prefix antigravity_cli_provider.py now writes
    (Task 5 of this spec) -- never any other .txt file in the system temp
    directory.

    max_age_s=3600 (1h) is comfortably larger than
    ProviderConfig.sync_call_timeout_s (300s) times max_retries (5) = the
    longest a single legitimate in-flight call could plausibly take, so
    this will never delete a file an actually-running call still owns.
    """
    removed_temp_files = 0
    pattern = os.path.join(tempfile.gettempdir(), "locpipe_agy_prompt_*.txt")
    for f in glob.glob(pattern):
        try:
            if time.time() - os.path.getmtime(f) > max_age_s:
                os.unlink(f)
                removed_temp_files += 1
        except OSError:
            pass

    removed_sessions = 0
    brain_dir = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    if brain_dir.is_dir():
        for session_dir in brain_dir.iterdir():
            if not session_dir.is_dir():
                continue
            try:
                if time.time() - session_dir.stat().st_mtime > max_age_s:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    removed_sessions += 1
            except OSError:
                pass

    return {"removed_temp_files": removed_temp_files, "removed_sessions": removed_sessions}
