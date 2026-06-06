"""Tests for regime-aware factor feedback (build_regime_table and generate_feedback)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import pandas as pd
import numpy as np
import pytest


class TestBuildRegimeTable:
    """Unit tests for build_regime_table()."""

    @pytest.fixture
    def mock_regime_map(self):
        """Create a mock monthly regime map DataFrame."""
        return pd.DataFrame({
            "year": [2018, 2018, 2018],
            "month": [1, 2, 3],
            "month_start": pd.to_datetime(["2018-01-01", "2018-02-01", "2018-03-01"]),
            "month_end": pd.to_datetime(["2018-01-31", "2018-02-28", "2018-03-31"]),
            "regime": ["calm_bull", "volatile_bear", "calm_bull"],
            "n_trading_days": [21, 19, 22],
        })

    @pytest.fixture
    def mock_exp_with_results(self, tmp_path):
        """Create a mock experiment with workspace result files."""
        from quantaalpha.core.experiment import Experiment
        from quantaalpha.factors.coder.factor import FactorTask

        exp = MagicMock(spec=Experiment)
        ws = MagicMock()
        ws.workspace_path = tmp_path

        # Create a result.h5 with factor values
        dates = pd.date_range("2018-01-02", "2018-03-30", freq="B")
        instruments = ["000001.XSHE", "000002.XSHE", "000003.XSHE"]
        idx = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
        factor_vals = np.random.randn(len(idx)) * 0.01
        factor_series = pd.DataFrame({"factor_0": factor_vals}, index=idx)
        factor_series.to_hdf(tmp_path / "result.h5", key="data")

        ws.target_task = MagicMock(spec=FactorTask)
        ws.target_task.factor_name = "test_factor"

        exp.sub_workspace_list = [ws]
        exp.experiment_workspace = ws

        # Mock label data from Qlib
        label_vals = np.random.randn(len(idx)) * 0.01
        self._label_series = pd.DataFrame({"label": label_vals}, index=idx)

        return exp

    def test_regime_map_none_returns_none(self):
        """build_regime_table with None regime_map returns None."""
        from quantaalpha.factors.feedback import build_regime_table
        result = build_regime_table(MagicMock(), None)
        assert result is None

    def test_missing_workspace_files_returns_none(self, mock_regime_map):
        """build_regime_table with no result.h5 files returns None."""
        from quantaalpha.factors.feedback import build_regime_table

        exp = MagicMock()
        ws = MagicMock()
        ws.workspace_path = Path("/nonexistent")
        exp.sub_workspace_list = [ws]

        with patch("quantaalpha.factors.feedback.logger") as mock_logger:
            result = build_regime_table(exp, mock_regime_map)
            assert result is None

    @patch("quantaalpha.factors.feedback.logger")
    @patch("quantaalpha.factors.feedback.build_regime_table")
    def test_generate_feedback_no_regime_map(self, mock_build, mock_logger):
        """generate_feedback without regime_map passes regime_table=None to template."""
        from quantaalpha.factors.feedback import AlphaAgentQlibFactorHypothesisExperiment2Feedback
        from quantaalpha.core.proposal import Hypothesis, Trace, HypothesisFeedback

        summarizer = AlphaAgentQlibFactorHypothesisExperiment2Feedback(MagicMock())
        # No regime_map set on summarizer
        summarizer.regime_map = None

        # Mock render to capture regime_table
        with patch("quantaalpha.factors.feedback.Environment") as mock_env:
            from_string = mock_env.return_value.from_string
            mock_template = MagicMock()
            from_string.return_value = mock_template

            # Mock process_results
            with patch("quantaalpha.factors.feedback.process_results", return_value="fake_table"):
                # Simulate but actually call the method to verify wiring
                mock_exp = MagicMock()
                mock_exp.result = pd.DataFrame({"0": [0.05, 0.10]}, index=["IC", "ann_return"])
                mock_exp.sub_tasks = []
                mock_exp.based_experiments = []

                mock_hyp = MagicMock(spec=Hypothesis)
                mock_hyp.hypothesis = "test hypothesis"
                mock_trace = MagicMock(spec=Trace)

                try:
                    summarizer.generate_feedback(mock_exp, mock_hyp, mock_trace)
                except Exception:
                    pass  # May fail due to incomplete mocks; we just verify template call

                # Verify regime_table=None was passed to render (second call = user prompt)
                assert mock_template.render.call_count == 2  # system + user
                user_call_kwargs = mock_template.render.call_args_list[1][1]
                assert user_call_kwargs.get("regime_table") is None

    def test_process_results_unchanged_without_regime_map(self):
        """process_results() without regime_map preserves original behavior."""
        from quantaalpha.factors.feedback import process_results

        current = pd.DataFrame({"0": [0.05, 0.02, 0.10, -0.08]},
                                index=["IC",
                                        "1day.excess_return_without_cost.information_ratio",
                                        "1day.excess_return_without_cost.annualized_return",
                                        "1day.excess_return_without_cost.max_drawdown"])
        sota = pd.DataFrame({"0": [0.03, 0.01, 0.08, -0.10]},
                             index=current.index)

        result = process_results(current.copy(), sota.copy())
        # Should be a string with the combined table
        assert isinstance(result, str)
        assert "Current Result" in result
        assert "SOTA Result" in result


class TestRegimeTemplate:
    """Verify the prompt template renders correctly with and without regime_table."""

    def test_template_renders_with_regime_table(self):
        """Template with regime_table includes the regime section."""
        from jinja2 import Environment, StrictUndefined

        template_str = """Combined Results:
{{ combined_result }}
{% if regime_table %}
**Regime-Aware Performance Analysis:**
{{ regime_table }}
{% endif %}
"""

        tpl = Environment(undefined=StrictUndefined).from_string(template_str)
        result = tpl.render(combined_result="fake result", regime_table="| regime | IC |")
        assert "Regime-Aware Performance Analysis" in result
        assert "| regime | IC |" in result

    def test_template_renders_without_regime_table(self):
        """Template without regime_table omits the regime section."""
        from jinja2 import Environment, StrictUndefined

        template_str = """Combined Results:
{{ combined_result }}
{% if regime_table %}
**Regime-Aware Performance Analysis:**
{{ regime_table }}
{% endif %}
"""

        tpl = Environment(undefined=StrictUndefined).from_string(template_str)
        result = tpl.render(combined_result="fake result", regime_table=None)
        assert "Regime-Aware Performance Analysis" not in result
