"""Tests for factor metrics, quality classification, cache scoping, and feature selection."""

from __future__ import annotations

import copy
import json
import hashlib
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from quantaalpha.backtest.ic_metrics import (
    FactorICMetrics,
    MetricContext,
    compute_daily_ic,
    aggregate_ic_metrics,
    classify_quality,
    compute_factor_metrics,
)
from quantaalpha.backtest.factor_loader import FactorLoader


# =========================================================================
# 6.1 Per-factor IC calculation
# =========================================================================


def _make_factor_label_data(
    n_dates: int = 5,
    n_instruments: int = 20,
    factor_a_coeff: float = 0.1,
    factor_b_coeff: float = -0.05,
    seed: int = 42,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Create synthetic factor_a, factor_b, and label series for testing IC computation."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="D")
    instruments = [f"stock_{i:04d}" for i in range(n_instruments)]

    idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])

    # Label: random return
    returns = rng.normal(0, 0.02, len(idx))
    label = pd.Series(returns, index=idx, name="LABEL0")

    # Factor A: positively correlated with label (+ noise)
    noise_a = rng.normal(0, 0.01, len(idx))
    factor_a = pd.Series(
        factor_a_coeff * returns + noise_a, index=idx, name="factor_a"
    )

    # Factor B: negatively correlated with label (+ noise)
    noise_b = rng.normal(0, 0.01, len(idx))
    factor_b = pd.Series(
        factor_b_coeff * returns + noise_b, index=idx, name="factor_b"
    )

    return factor_a, factor_b, label


class TestDailyIC:
    def test_two_factors_produce_different_ic(self):
        """Two factors against the same label must give distinct IC / Rank IC."""
        factor_a, factor_b, label = _make_factor_label_data(
            factor_a_coeff=0.1, factor_b_coeff=-0.05, seed=42
        )

        daily_ic_a, daily_ric_a, n_days_a, n_obs_a = compute_daily_ic(factor_a, label)
        daily_ic_b, daily_ric_b, n_days_b, n_obs_b = compute_daily_ic(factor_b, label)

        metrics_a = aggregate_ic_metrics(daily_ic_a, daily_ric_a)
        metrics_b = aggregate_ic_metrics(daily_ic_b, daily_ric_b)

        # Both factors have data
        assert metrics_a.n_days >= 3
        assert metrics_b.n_days >= 3

        # IC should have opposite signs
        assert metrics_a.IC > 0, "Factor A (positive coeff) should have positive IC"
        assert metrics_b.IC < 0, "Factor B (negative coeff) should have negative IC"
        assert metrics_a.Rank_IC > metrics_b.Rank_IC, (
            f"Expected Rank_IC_A ({metrics_a.Rank_IC}) > Rank_IC_B ({metrics_b.Rank_IC})"
        )

    def test_insufficient_overlap_returns_empty(self):
        """When factor and label have zero overlapping indices, return empty series."""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        instruments = [f"stock_{i:04d}" for i in range(5)]

        idx_a = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
        idx_b = pd.MultiIndex.from_product(
            [pd.date_range("2025-01-01", periods=3, freq="D"), instruments],
            names=["datetime", "instrument"],
        )

        factor = pd.Series(np.random.randn(len(idx_a)), index=idx_a)
        label = pd.Series(np.random.randn(len(idx_b)), index=idx_b)

        daily_ic, daily_ric, n_days, n_obs = compute_daily_ic(factor, label)
        assert len(daily_ic) == 0
        assert n_days == 0

    def test_min_instruments_filter(self):
        """Days with too few instruments are skipped."""
        dates = pd.date_range("2024-01-01", periods=3, freq="D")
        instruments = [f"stock_{i:04d}" for i in range(2)]  # only 2 instruments

        idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
        factor = pd.Series(np.random.randn(len(idx)), index=idx)
        label = pd.Series(np.random.randn(len(idx)), index=idx)

        # min_instruments=3 should reject all days
        daily_ic, daily_ric, n_days, n_obs = compute_daily_ic(factor, label, min_instruments=3)
        assert n_days == 0


# =========================================================================
# 6.2 / 6.3 Library serialization and API conversion
# =========================================================================


class TestFactorMetricsSerialization:
    def test_factor_metrics_to_dict(self):
        """FactorICMetrics serializes to the expected schema."""
        metrics = FactorICMetrics(
            IC=0.05,
            IC_std=0.02,
            ICIR=2.5,
            Rank_IC=0.04,
            Rank_IC_std=0.015,
            Rank_ICIR=2.67,
            n_days=120,
            n_obs=24000,
        )
        d = metrics.to_dict()
        assert d["IC"] == 0.05
        assert d["IC_std"] == 0.02
        assert d["ICIR"] == 2.5
        assert d["Rank_IC"] == 0.04
        assert d["Rank_IC_std"] == 0.015
        assert d["Rank_ICIR"] == 2.67
        assert d["n_days"] == 120
        assert d["n_obs"] == 24000
        assert len(d) == 8

    def test_metric_context_serialization(self):
        """MetricContext serializes to the expected fields."""
        ctx = MetricContext(
            provider_uri="~/.qlib/qlib_data/cn_data",
            market="csi300",
            start_time="2020-01-01",
            end_time="2024-12-31",
            label_expr="Ref($close, -2) / Ref($close, -1) - 1",
        )
        d = ctx.to_dict()
        assert d["market"] == "csi300"
        assert d["label_expr"] == "Ref($close, -2) / Ref($close, -1) - 1"

    def test_classify_quality(self):
        """Quality classification from FactorICMetrics."""
        # High: |Rank_IC| >= 0.03, n_days >= 10
        assert classify_quality(FactorICMetrics(Rank_IC=0.04, n_days=100)) == "high"
        assert classify_quality(FactorICMetrics(Rank_IC=-0.04, n_days=100)) == "high"

        # Medium: |Rank_IC| >= 0.01, n_days >= 10
        assert classify_quality(FactorICMetrics(Rank_IC=0.02, n_days=100)) == "medium"
        assert classify_quality(FactorICMetrics(Rank_IC=-0.02, n_days=100)) == "medium"
        assert classify_quality(FactorICMetrics(Rank_IC=0.029, n_days=100)) == "medium"

        # Low: |Rank_IC| < 0.01, n_days >= 10
        assert classify_quality(FactorICMetrics(Rank_IC=0.005, n_days=100)) == "low"
        assert classify_quality(FactorICMetrics(Rank_IC=-0.005, n_days=100)) == "low"

        # Unknown: n_days < 10
        assert classify_quality(FactorICMetrics(Rank_IC=0.05, n_days=5)) == "unknown"
        assert classify_quality(FactorICMetrics(Rank_IC=0.005, n_days=5)) == "unknown"

        # Unknown: no metrics
        assert classify_quality(None) == "unknown"

    def test_classify_quality_experiment_metrics_not_used(self):
        """Factor with experiment metrics but no factor_metrics → unknown."""
        # This simulates a legacy entry: backtest_results present but factor_metrics absent
        assert classify_quality(None) == "unknown"


# =========================================================================
# 6.4 Loader selection
# =========================================================================


def _make_library_json(
    factors: list[dict], tmp_path: Path, filename: str = "test_library.json"
) -> str:
    """Write a temporary factor library JSON and return its path."""
    data = {"metadata": {"version": "1.0"}, "factors": {}}
    for f in factors:
        fid = hashlib.md5(f["factor_name"].encode()).hexdigest()[:16]
        entry = {
            "factor_id": fid,
            "factor_name": f["factor_name"],
            "factor_expression": f["factor_expression"],
            "factor_description": f.get("factor_description", ""),
            "factor_metrics": f.get("factor_metrics", {}),
            "quality": f.get("quality", "unknown"),
            "metadata": {"created_at": f.get("created_at", "2024-01-01T00:00:00")},
        }
        data["factors"][fid] = entry
    path = tmp_path / filename
    with open(path, "w") as f:
        json.dump(data, f)
    return str(path)


class TestLoaderSelection:
    def test_deduplicate_expressions(self, tmp_path):
        """Duplicate expressions collapse to one factor (first occurrence kept)."""
        factors = [
            {"factor_name": "A", "factor_expression": "close / delay(close, 1) - 1"},
            {"factor_name": "B", "factor_expression": "close / delay(close, 1) - 1"},
            {"factor_name": "C", "factor_expression": "close / delay(close, 1) - 1"},
        ]
        lib_path = _make_library_json(factors, tmp_path)

        config = {
            "factor_source": {
                "type": "custom",
                "custom": {"json_files": [lib_path], "max_factors": None},
            }
        }
        loader = FactorLoader(config)
        _, custom = loader.load_factors()
        # Only one factor after dedup
        assert len(custom) == 1
        assert custom[0]["factor_name"] == "A"

    def test_sort_by_rank_ic(self, tmp_path):
        """Factors are sorted by abs(Rank_IC) descending."""
        factors = [
            {
                "factor_name": "LowIC",
                "factor_expression": "expr_a",
                "factor_metrics": {"Rank_IC": 0.01, "ICIR": 0.3},
            },
            {
                "factor_name": "HighIC",
                "factor_expression": "expr_b",
                "factor_metrics": {"Rank_IC": 0.05, "ICIR": 0.8},
            },
            {
                "factor_name": "MidIC",
                "factor_expression": "expr_c",
                "factor_metrics": {"Rank_IC": -0.03, "ICIR": 0.6},
            },
        ]
        lib_path = _make_library_json(factors, tmp_path)

        config = {
            "factor_source": {
                "type": "custom",
                "custom": {"json_files": [lib_path], "max_factors": None},
            }
        }
        loader = FactorLoader(config)
        _, custom = loader.load_factors()
        names = [f["factor_name"] for f in custom]
        # HighIC (0.05) > MidIC (0.03) > LowIC (0.01)
        assert names == ["HighIC", "MidIC", "LowIC"], f"Got {names}"

    def test_max_factors_cap(self, tmp_path):
        """max_factors limits the number of returned factors."""
        factors = []
        for i in range(10):
            factors.append(
                {
                    "factor_name": f"F{i}",
                    "factor_expression": f"expr_{i}",
                    "factor_metrics": {"Rank_IC": 0.01 + i * 0.005, "ICIR": 0.1},
                }
            )
        lib_path = _make_library_json(factors, tmp_path)

        config = {
            "factor_source": {
                "type": "custom",
                "custom": {"json_files": [lib_path], "max_factors": 3},
            }
        }
        loader = FactorLoader(config)
        _, custom = loader.load_factors()
        assert len(custom) == 3
        # Top 3 by abs(Rank_IC)
        assert custom[0]["factor_name"] == "F9"
        assert custom[1]["factor_name"] == "F8"
        assert custom[2]["factor_name"] == "F7"

    def test_unlimited_when_max_factors_zero(self, tmp_path):
        """max_factors=0 or null gives all factors."""
        factors = []
        for i in range(10):
            factors.append(
                {
                    "factor_name": f"F{i}",
                    "factor_expression": f"expr_{i}",
                    "factor_metrics": {"Rank_IC": 0.01, "ICIR": 0.1},
                }
            )
        lib_path = _make_library_json(factors, tmp_path)

        for max_val in [None, 0]:
            config = {
                "factor_source": {
                    "type": "custom",
                    "custom": {"json_files": [lib_path], "max_factors": max_val},
                }
            }
            loader = FactorLoader(config)
            _, custom = loader.load_factors()
            assert len(custom) == 10

    def test_factors_without_metrics_sort_last(self, tmp_path):
        """Factors without factor_metrics appear after sorted factors with metrics."""
        factors = [
            {
                "factor_name": "WithMetrics",
                "factor_expression": "expr_a",
                "factor_metrics": {"Rank_IC": 0.02, "ICIR": 0.3},
            },
            {
                "factor_name": "NoMetrics",
                "factor_expression": "expr_b",
                "factor_metrics": {},
            },
            {
                "factor_name": "BetterMetrics",
                "factor_expression": "expr_c",
                "factor_metrics": {"Rank_IC": 0.05, "ICIR": 0.8},
            },
        ]
        lib_path = _make_library_json(factors, tmp_path)

        config = {
            "factor_source": {
                "type": "custom",
                "custom": {"json_files": [lib_path], "max_factors": None},
            }
        }
        loader = FactorLoader(config)
        _, custom = loader.load_factors()
        names = [f["factor_name"] for f in custom]
        assert names == ["BetterMetrics", "WithMetrics", "NoMetrics"], f"Got {names}"


# =========================================================================
# 6.5 Cache behavior
# =========================================================================


class TestCacheScoping:
    def test_different_market_produces_different_cache_key(self):
        """Scoped cache key changes when market changes."""
        ctx1 = MetricContext(market="csi300", start_time="2020-01-01", end_time="2024-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")
        ctx2 = MetricContext(market="csi500", start_time="2020-01-01", end_time="2024-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")

        from quantaalpha.factors.library import FactorLibraryManager
        key1 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx1))
        key2 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx2))
        assert key1 != key2

    def test_different_date_range_produces_different_cache_key(self):
        """Scoped cache key changes when date range changes."""
        ctx1 = MetricContext(market="csi300", start_time="2020-01-01", end_time="2023-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")
        ctx2 = MetricContext(market="csi300", start_time="2021-01-01", end_time="2024-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")

        from quantaalpha.factors.library import FactorLibraryManager
        key1 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx1))
        key2 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx2))
        assert key1 != key2

    def test_same_scope_produces_identical_cache_key(self):
        """Same scope produces the same cache key."""
        ctx = MetricContext(market="csi300", start_time="2020-01-01", end_time="2024-12-31",
                             provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")

        from quantaalpha.factors.library import FactorLibraryManager
        key1 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx))
        key2 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx))
        assert key1 == key2

    def test_scoped_cache_key_includes_label(self):
        """Different label expression produces different cache key."""
        ctx1 = MetricContext(market="csi300", start_time="2020-01-01", end_time="2024-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -2)/Ref($close, -1)-1")
        ctx2 = MetricContext(market="csi300", start_time="2020-01-01", end_time="2024-12-31",
                              provider_uri="~/.qlib/qlib_data/cn_data", label_expr="Ref($close, -5)/$close-1")

        from quantaalpha.factors.library import FactorLibraryManager
        key1 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx1))
        key2 = FactorLibraryManager._make_scoped_cache_key("expr", asdict(ctx2))
        assert key1 != key2


class TestCacheInstrumentValidation:
    """Tests for cache_validation module."""

    def test_should_reject_disjoint_sets(self):
        """Completely disjoint instrument sets are rejected."""
        from quantaalpha.backtest.cache_validation import should_reject_cached_factor
        assert should_reject_cached_factor(["A", "B"], ["C", "D"]) is True

    def test_should_reject_below_threshold(self):
        """Instrument sets below 80% overlap are rejected."""
        from quantaalpha.backtest.cache_validation import should_reject_cached_factor
        # 2 cached, 1 matches => 50% overlap < 80% => reject
        assert should_reject_cached_factor(["A", "B"], ["A", "C"]) is True
        # 5 cached, 1 matches => 20% overlap < 80% => reject
        assert should_reject_cached_factor(["A", "B", "C", "D", "E"], ["A"], min_overlap=0.80) is True

    def test_should_accept_above_threshold(self):
        """Instrument sets at or above 80% overlap are accepted."""
        from quantaalpha.backtest.cache_validation import should_reject_cached_factor
        # 5 cached, 4 match => 80% overlap => accept
        assert should_reject_cached_factor(["A", "B", "C", "D", "E"], ["A", "B", "C", "D", "F"], min_overlap=0.80) is False
        # All match => 100% => accept
        assert should_reject_cached_factor(["A", "B", "C"], ["A", "B", "C", "D"], min_overlap=0.80) is False

    def test_empty_sets_not_rejected(self):
        """Empty sets should not trigger rejection."""
        from quantaalpha.backtest.cache_validation import should_reject_cached_factor
        assert should_reject_cached_factor(None, ["A", "B"]) is False
        assert should_reject_cached_factor(["A", "B"], None) is False

    def test_instrument_overlap_count(self):
        """Instrument overlap count is correct."""
        from quantaalpha.backtest.cache_validation import instrument_overlap_count
        assert instrument_overlap_count(["A", "B", "C"], ["A", "D", "E"]) == 1
        assert instrument_overlap_count(["A", "B"], ["C", "D"]) == 0


# =========================================================================
# 6.6 Smoke test helpers
# =========================================================================


class TestComputeFactorMetrics:
    """Integration-style tests for the compute_factor_metrics entry point."""

    def test_compute_factor_metrics_returns_expected_schema(self):
        """compute_factor_metrics returns dict with factor_metrics and metric_context."""
        factor_a, _, label = _make_factor_label_data(seed=42)
        ctx = MetricContext(
            provider_uri="test", market="csi300", start_time="2024-01-01",
            end_time="2024-01-05", label_expr="test_label",
        )
        result = compute_factor_metrics(factor_a, label, metric_context=ctx)
        assert "factor_metrics" in result
        fm = result["factor_metrics"]
        for key in ("IC", "IC_std", "ICIR", "Rank_IC", "Rank_IC_std", "Rank_ICIR", "n_days", "n_obs"):
            assert key in fm, f"Missing key in factor_metrics: {key}"
        assert "metric_context" in result
        assert result["metric_context"]["market"] == "csi300"
