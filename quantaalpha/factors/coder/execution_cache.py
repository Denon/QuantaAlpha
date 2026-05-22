from __future__ import annotations

from pathlib import Path


FACTOR_RUNTIME_CACHE_FILES = (
    "function_lib.py",
    "grouping.py",
    "execution_utils.py",
    "data_files.py",
)


def factor_runtime_fingerprint(
    runtime_dir: Path | str | None = None,
    runtime_files: tuple[str, ...] = FACTOR_RUNTIME_CACHE_FILES,
) -> str:
    """Return a stable fingerprint source for runtime files used by factor.py."""
    base_dir = Path(runtime_dir) if runtime_dir is not None else Path(__file__).parent
    chunks = []
    for file_name in runtime_files:
        path = base_dir / file_name
        if path.exists():
            chunks.append(f"{file_name}\n{path.read_text()}")
    return "\n\n".join(chunks)
