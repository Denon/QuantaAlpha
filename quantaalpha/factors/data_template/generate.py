import qlib

import os
import pandas as pd
from pathlib import Path

_provider = os.environ.get("QLIB_DATA_DIR", os.environ.get("QLIB_PROVIDER_URI", "~/.qlib/qlib_data/cn_data"))
qlib.init(provider_uri=_provider)
from qlib.data import D

instruments = D.instruments()
fields = ["$open", "$close", "$high", "$low", "$volume"]  # , "$amount", "$turn", "$pettm", "$pbmrq"
data = D.features(instruments, fields, freq="day").swaplevel().sort_index().loc["2015-01-01":].sort_index()

# Calculate return
data["$return"] = data.groupby(level=0)["$close"].pct_change().fillna(0)

# =====================================================================
# Merge pre-computed external factors as base fields ($prefixed columns)
# =====================================================================
_script_dir = Path(__file__).resolve().parent
_external_path = _script_dir.parent.parent.parent / "data" / "external" / "factors_2016_2025.parquet"
if _external_path.exists():
    _ext_df = pd.read_parquet(_external_path)
    _ext_df["date"] = pd.to_datetime(_ext_df["date"])
    _ext_df = _ext_df.set_index(["date", "instrument"]).sort_index()
    _ext_df.index.names = ["datetime", "instrument"]
    _ext_df = _ext_df.add_prefix("$")
    _common_idx = data.index.intersection(_ext_df.index)
    if len(_common_idx) > 0:
        data = data.join(_ext_df, how="left")
        print(f"Merged external columns: {[c for c in data.columns if c not in ['$open','$close','$high','$low','$volume','$return']]}")
    else:
        print("Warning: external data has zero overlap with Qlib data index")
else:
    print(f"Warning: external data not found at {_external_path}")

print(data)
data.to_hdf(_script_dir / "daily_pv_all.h5", key="data")

fields = ["$open", "$close", "$high", "$low", "$volume"]  # , "$amount", "$turn", "$pettm", "$pbmrq"
data = (
    (
        D.features(instruments, fields, freq="day")
        .swaplevel()
        .sort_index()
    )
    .swaplevel()
    .loc[data.reset_index()["instrument"].unique()[:100]]
    .swaplevel()
    .sort_index()
)

# Calculate return
data["$return"] = data.groupby(level=0)["$close"].pct_change().fillna(0)

# Merge external factors into debug data too
if _external_path.exists():
    _common_idx_debug = data.index.intersection(_ext_df.index)
    if len(_common_idx_debug) > 0:
        data = data.join(_ext_df, how="left")

print(data)
data.to_hdf(_script_dir / "daily_pv_debug.h5", key="data")