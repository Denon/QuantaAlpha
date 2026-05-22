from __future__ import annotations

import os
import shutil
from pathlib import Path


def _remove_existing(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _link_or_copy(source: Path, target: Path) -> None:
    source = source.absolute()
    _remove_existing(target)
    try:
        os.symlink(source, target, target_is_directory=source.is_dir())
    except OSError:
        if source.is_dir():
            shutil.copytree(source, target)
            return
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


def _ensure_daily_pv_alias(workspace_path: Path) -> None:
    canonical = workspace_path / "daily_pv.h5"
    if canonical.exists() or canonical.is_symlink():
        return

    for fallback_name in ("daily_pv_debug.h5", "daily_pv_all.h5"):
        fallback = workspace_path / fallback_name
        if fallback.exists() or fallback.is_symlink():
            _link_or_copy(fallback, canonical)
            return


def link_factor_data_files(source_data_path: Path | str, workspace_path: Path | str) -> None:
    source_data_path = Path(source_data_path).absolute()
    workspace_path = Path(workspace_path)
    workspace_path.mkdir(parents=True, exist_ok=True)

    for source_file_path in source_data_path.iterdir():
        workspace_data_file_path = workspace_path / source_file_path.name
        _link_or_copy(source_file_path, workspace_data_file_path)

    _ensure_daily_pv_alias(workspace_path)

