#!/usr/bin/env python3
"""Clean up today's buggy factors, keeping size and beta."""
import json
from pathlib import Path

path = Path("data/factorlib/all_factors_library.json")
with open(path) as f:
    lib = json.load(f)

factors = lib["factors"]
today = "2026-05-24"
keep_names = {"size", "beta"}

to_delete = [
    fid for fid, finfo in factors.items()
    if finfo.get("metadata", {}).get("created_at", "").startswith(today)
    and finfo.get("factor_name") not in keep_names
]

for fid in to_delete:
    del factors[fid]

lib["metadata"]["total_factors"] = len(factors)
lib["metadata"]["last_updated"] = "2026-05-24T17:50:00"

with open(path, "w", encoding="utf-8") as f:
    json.dump(lib, f, ensure_ascii=False, indent=2, default=str)

print(f"Deleted {len(to_delete)} factors, {len(factors)} remaining")
