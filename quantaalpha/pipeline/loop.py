"""
Model workflow with session control.
"""

import time
import pandas as pd
from typing import Any, Optional

from quantaalpha.pipeline.settings import BaseFacSetting
from quantaalpha.core.developer import Developer
from quantaalpha.core.proposal import (
    Hypothesis2Experiment,
    HypothesisExperiment2Feedback,
    HypothesisGen,  
    Trace,
)
from quantaalpha.core.scenario import Scenario
from quantaalpha.core.utils import import_class
from quantaalpha.log import logger
from quantaalpha.log.time import measure_time
from quantaalpha.utils.workflow import LoopBase, LoopMeta
from quantaalpha.core.exception import FactorEmptyError
import threading


import datetime
import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tqdm.auto import tqdm

from quantaalpha.core.exception import CoderError
from quantaalpha.log import logger
from functools import wraps

# Decorator: check stop_event before invoking the function

def stop_event_check(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if STOP_EVENT is not None and STOP_EVENT.is_set():
            raise Exception("Operation stopped due to stop_event flag.")
        return func(self, *args, **kwargs)
    return wrapper


class AlphaAgentLoop(LoopBase, metaclass=LoopMeta):
    skip_loop_error = (FactorEmptyError,)
    
    @measure_time
    def __init__(
        self, 
        PROP_SETTING: BaseFacSetting, 
        potential_direction, 
        stop_event: threading.Event, 
        use_local: bool = True,
        strategy_suffix: str = "",
        evolution_phase: str = "original",
        trajectory_id: str = "",
        parent_trajectory_ids: list = None,
        direction_id: int = 0,
        round_idx: int = 0,
        quality_gate_config: dict = None,
    ):
        with logger.tag("init"):
            self.use_local = use_local
            # Store initial direction for factor provenance
            self.potential_direction = potential_direction

            # Evolution-related attributes
            self.strategy_suffix = strategy_suffix
            self.evolution_phase = evolution_phase  # original / mutation / crossover
            self.trajectory_id = trajectory_id
            self.parent_trajectory_ids = parent_trajectory_ids or []
            self.direction_id = direction_id
            self.round_idx = round_idx  # 0=original, 1=mutation, 2=crossover, ...

            # Quality gate config
            self.quality_gate_config = quality_gate_config or {}

            # For trajectory collection
            self._last_hypothesis = None
            self._last_experiment = None
            self._last_feedback = None
            
            logger.info(f"Initialized AlphaAgentLoop, backtest in {'local' if use_local else 'Docker'}")
            if potential_direction:
                logger.info(f"Initial direction: {potential_direction}")
            if evolution_phase != "original":
                logger.info(f"Evolution phase: {evolution_phase}, round: {round_idx}, trajectory_id: {trajectory_id}")

            consistency_enabled = self.quality_gate_config.get("consistency_enabled", False)
            complexity_enabled = self.quality_gate_config.get("complexity_enabled", True)
            redundancy_enabled = self.quality_gate_config.get("redundancy_enabled", True)
            logger.info(f"Quality gate: consistency={'on' if consistency_enabled else 'off'}, "
                       f"complexity={'on' if complexity_enabled else 'off'}, "
                       f"redundancy={'on' if redundancy_enabled else 'off'}")
                
            scen: Scenario = import_class(PROP_SETTING.scen)(use_local=use_local)
            logger.log_object(scen, tag="scenario")

            # If strategy suffix is set, append it to the direction
            effective_direction = potential_direction
            if strategy_suffix:
                effective_direction = (potential_direction or "") + "\n" + strategy_suffix
            
            self.hypothesis_generator: HypothesisGen = import_class(PROP_SETTING.hypothesis_gen)(scen, effective_direction)
            logger.log_object(self.hypothesis_generator, tag="hypothesis generator")

            # Pass consistency check config into factor constructor
            self.factor_constructor: Hypothesis2Experiment = import_class(PROP_SETTING.hypothesis2experiment)(
                consistency_enabled=consistency_enabled
            )
            logger.log_object(self.factor_constructor, tag="experiment generation")

            self.coder: Developer = import_class(PROP_SETTING.coder)(scen)
            logger.log_object(self.coder, tag="coder")
            
            self.runner: Developer = import_class(PROP_SETTING.runner)(scen)
            logger.log_object(self.runner, tag="runner")

            self.summarizer: HypothesisExperiment2Feedback = import_class(PROP_SETTING.summarizer)(scen)
            logger.log_object(self.summarizer, tag="summarizer")
            self.trace = Trace(scen=scen)
            
            global STOP_EVENT
            STOP_EVENT = stop_event
            super().__init__()

    @classmethod
    def load(cls, path, use_local: bool = True):
        """Load existing session."""
        instance = super().load(path)
        instance.use_local = use_local
        logger.info(f"Loaded AlphaAgentLoop, backtest in {'local' if use_local else 'Docker'}")
        return instance

    @measure_time
    @stop_event_check
    def factor_propose(self, prev_out: dict[str, Any]):
        """Propose hypothesis as the basis for factor construction."""
        with logger.tag("r"):  
            idea = self.hypothesis_generator.gen(self.trace)
            logger.log_object(idea, tag="hypothesis generation")
            self._last_hypothesis = idea
        return idea

    @measure_time
    @stop_event_check
    def factor_construct(self, prev_out: dict[str, Any]):
        """Construct multiple factors from the hypothesis."""
        with logger.tag("r"): 
            factor = self.factor_constructor.convert(prev_out["factor_propose"], self.trace)
            logger.log_object(factor.sub_tasks, tag="experiment generation")
        return factor

    @measure_time
    @stop_event_check
    def factor_calculate(self, prev_out: dict[str, Any]):
        """Compute factor values from factor expressions."""
        with logger.tag("d"):  # develop
            factor = self.coder.develop(prev_out["factor_construct"])
            logger.log_object(factor.sub_workspace_list, tag="coder result")
        return factor
    

    @measure_time
    @stop_event_check
    def factor_backtest(self, prev_out: dict[str, Any]):
        """Run backtest for factors."""
        with logger.tag("ef"):  # evaluate and feedback
            logger.info(f"Start factor backtest (Local: {self.use_local})")
            exp = self.runner.develop(prev_out["factor_calculate"], use_local=self.use_local)
            if exp is None:
                logger.error(f"Factor extraction failed.")
                raise FactorEmptyError("Factor extraction failed.")
            logger.log_object(exp, tag="runner result")
            self._last_experiment = exp
        return exp

    @measure_time
    @stop_event_check
    def feedback(self, prev_out: dict[str, Any]):
        feedback = self.summarizer.generate_feedback(prev_out["factor_backtest"], prev_out["factor_propose"], self.trace)
        with logger.tag("ef"):  # evaluate and feedback
            logger.log_object(feedback, tag="feedback")
        self.trace.hist.append((prev_out["factor_propose"], prev_out["factor_backtest"], feedback))
        
        self._last_feedback = feedback

        # Auto-save factors to unified factor library
        try:
            import os
            from pathlib import Path
            from quantaalpha.factors.library import FactorLibraryManager
            
            # Project root: loop.py -> pipeline/ -> quantaalpha/ -> project_root/
            project_root = Path(__file__).resolve().parent.parent.parent

            experiment_id = "unknown"
            if hasattr(self, 'session_folder') and self.session_folder:
                parts = Path(self.session_folder).parts
                for part in parts:
                    if part.startswith("202") and len(part) > 10:
                        experiment_id = part
                        break

            round_number = self.round_idx

            hypothesis_text = None
            if prev_out.get("factor_propose"):
                hypothesis_text = str(prev_out["factor_propose"])

            planning_direction = getattr(self, 'potential_direction', None)
            user_initial_direction = getattr(self, 'user_initial_direction', None)

            evolution_phase = getattr(self, 'evolution_phase', 'original')
            trajectory_id = getattr(self, 'trajectory_id', '')
            parent_trajectory_ids = getattr(self, 'parent_trajectory_ids', [])

            # Factor library filename can be customized via env FACTOR_LIBRARY_SUFFIX
            library_suffix = os.environ.get('FACTOR_LIBRARY_SUFFIX', '')
            if library_suffix:
                library_filename = f"all_factors_library_{library_suffix}.json"
            else:
                library_filename = "all_factors_library.json"
            factorlib_dir = project_root / "data" / "factorlib"
            factorlib_dir.mkdir(parents=True, exist_ok=True)
            library_path = factorlib_dir / library_filename
            manager = FactorLibraryManager(str(library_path))
            # Pass per-factor IC metrics if computed by the backtest step
            factor_metrics_dict = prev_out.get("per_factor_ic_metrics", {})
            metric_context = prev_out.get("metric_context")

            # If metrics not provided by the pipeline, compute them from experiment results
            if not factor_metrics_dict:
                try:
                    computed = self._compute_experiment_per_factor_metrics(
                        prev_out["factor_backtest"]
                    )
                    if computed:
                        factor_metrics_dict, metric_context = computed
                except Exception as e:
                    logger.debug(f"Per-factor metrics computation skipped: {e}")

            manager.add_factors_from_experiment(
                experiment=prev_out["factor_backtest"],
                experiment_id=experiment_id,
                round_number=round_number,
                hypothesis=hypothesis_text,
                feedback=feedback,
                initial_direction=planning_direction,
                user_initial_direction=user_initial_direction,
                planning_direction=planning_direction,
                evolution_phase=evolution_phase,
                trajectory_id=trajectory_id,
                parent_trajectory_ids=parent_trajectory_ids,
                factor_metrics_dict=factor_metrics_dict,
                metric_context=metric_context,
            )
            logger.info(f"Saved factors to library: {library_path} (phase={evolution_phase})")
        except Exception as e:
            logger.warning(f"Failed to save factors to library: {e}")
    
    def _get_trajectory_data(self) -> dict[str, Any]:
        """
        Get trajectory data for the current round (used by evolution controller).
        Method name is prefixed with underscore so the workflow system does not treat it as a step.
        Returns:
            Dict with hypothesis, experiment, feedback, etc.
        """
        return {
            "hypothesis": self._last_hypothesis,
            "experiment": self._last_experiment,
            "feedback": self._last_feedback,
            "direction_id": self.direction_id,
            "evolution_phase": self.evolution_phase,
            "trajectory_id": self.trajectory_id,
            "parent_trajectory_ids": self.parent_trajectory_ids,
            "loop_idx": self.loop_idx,
            "round_idx": self.round_idx,
        }

    def _compute_experiment_per_factor_metrics(self, experiment) -> tuple[dict, Optional[dict]]:
        """Compute per-factor IC metrics from experiment results for library persistence.

        Reads factor values from each sub-workspace's result.h5, computes the
        forward-return label via Qlib, and returns (metrics_by_factor_name, metric_context).
        Returns ({}, None) if computation is not possible.
        """
        import pandas as pd
        from pathlib import Path as _Path

        sub_workspaces = getattr(experiment, "sub_workspace_list", [])
        sub_tasks = getattr(experiment, "sub_tasks", [])
        if not sub_workspaces or not sub_tasks:
            return {}, None

        # Read factor values from each workspace's result.h5
        factor_values = {}
        for idx, ws in enumerate(sub_workspaces):
            ws_path = getattr(ws, "workspace_path", None)
            if ws_path is None:
                continue
            h5_file = _Path(ws_path) / "result.h5"
            if not h5_file.exists():
                continue

            factor_name = None
            if idx < len(sub_tasks):
                factor_name = getattr(sub_tasks[idx], "factor_name", None)
            if not factor_name:
                factor_name = _Path(ws_path).name

            try:
                data = pd.read_hdf(h5_file)
            except Exception:
                continue

            if isinstance(data, pd.DataFrame) and data.shape[1] > 0:
                factor_values[factor_name] = data.iloc[:, 0]
            elif isinstance(data, pd.Series):
                factor_values[factor_name] = data

        if not factor_values:
            return {}, None

        # Detect date range and instruments from factor data
        all_dates = []
        all_instruments = set()
        for series in factor_values.values():
            if isinstance(series.index, pd.MultiIndex):
                all_dates.extend(series.index.get_level_values("datetime"))
                all_instruments.update(series.index.get_level_values("instrument"))

        if not all_dates:
            return {}, None

        start_time = min(all_dates).strftime("%Y-%m-%d")
        end_time = max(all_dates).strftime("%Y-%m-%d")
        instruments = list(all_instruments)

        # Read label expression and data config from the experiment's template config
        provider_uri = ""
        market = ""
        label_expr = "Ref($close, -2)/Ref($close, -1) - 1"
        try:
            exp_ws = getattr(experiment, "experiment_workspace", None)
            if exp_ws is not None:
                tmpl = getattr(exp_ws, "template_folder_path", None)
                if tmpl is not None:
                    import yaml as _yaml
                    tmpl_path = _Path(tmpl) / "conf_baseline.yaml"
                    if tmpl_path.exists():
                        with open(tmpl_path) as _f:
                            tmpl_cfg = _yaml.safe_load(_f)
                        dhc = tmpl_cfg.get("data_handler_config", {})
                        qinit = tmpl_cfg.get("qlib_init", {})
                        provider_uri = qinit.get("provider_uri", provider_uri)
                        market = dhc.get("instruments", "")
                        label_cfg = dhc.get("data_loader", {}).get("kwargs", {}).get("config", {}).get("label", [])
                        if label_cfg and len(label_cfg) > 0 and len(label_cfg[0]) > 0:
                            label_expr = label_cfg[0][0]
        except Exception as e:
            logger.debug(f"Cannot read template config: {e}")

        # Compute the forward-return label via Qlib
        try:
            from qlib.data import D as _D
            label_df = _D.features(
                instruments, [label_expr],
                start_time=start_time, end_time=end_time, freq="day",
            )
            label_df.columns = ["LABEL0"]
            # Normalize to canonical (datetime, instrument) order
            if list(label_df.index.names) == ["instrument", "datetime"]:
                label_df = label_df.swaplevel().sort_index()
        except Exception as e:
            logger.debug(f"Cannot compute label for per-factor metrics: {e}")
            return {}, None

        # Build metric context with all fields for staleness detection
        from quantaalpha.backtest.ic_metrics import MetricContext
        ctx = MetricContext(
            provider_uri=provider_uri,
            market=market,
            start_time=start_time,
            end_time=end_time,
            label_expr=label_expr,
        )

        # Compute metrics per factor
        from quantaalpha.backtest.ic_metrics import compute_factor_metrics
        result = {}
        for factor_name, series in factor_values.items():
            # Normalize factor index to canonical (datetime, instrument) order
            if isinstance(series.index, pd.MultiIndex) and series.index.names == ["instrument", "datetime"]:
                series = series.swaplevel().sort_index()
            try:
                metrics_result = compute_factor_metrics(
                    series, label_df["LABEL0"], metric_context=ctx,
                )
                result[factor_name] = metrics_result
            except Exception as e:
                logger.debug(f"Per-factor IC failed [{factor_name}]: {e}")

        return result, ctx.to_dict()




class BacktestLoop(LoopBase, metaclass=LoopMeta):
    skip_loop_error = (FactorEmptyError,)
    @measure_time
    def __init__(self, PROP_SETTING: BaseFacSetting, factor_path=None):
        with logger.tag("init"):

            self.factor_path = factor_path

            scen: Scenario = import_class(PROP_SETTING.scen)()
            logger.log_object(scen, tag="scenario")

            self.hypothesis_generator: HypothesisGen = import_class(PROP_SETTING.hypothesis_gen)(scen)
            logger.log_object(self.hypothesis_generator, tag="hypothesis generator")

            self.factor_constructor: Hypothesis2Experiment = import_class(PROP_SETTING.hypothesis2experiment)(factor_path=factor_path)
            logger.log_object(self.factor_constructor, tag="experiment generation")

            self.coder: Developer = import_class(PROP_SETTING.coder)(scen, with_feedback=False, with_knowledge=False, knowledge_self_gen=False)
            logger.log_object(self.coder, tag="coder")
            
            self.runner: Developer = import_class(PROP_SETTING.runner)(scen)
            logger.log_object(self.runner, tag="runner")

            self.summarizer: HypothesisExperiment2Feedback = import_class(PROP_SETTING.summarizer)(scen)
            logger.log_object(self.summarizer, tag="summarizer")
            self.trace = Trace(scen=scen)
            super().__init__()

    def factor_propose(self, prev_out: dict[str, Any]):
        """
        Market hypothesis on which factors are built
        """
        with logger.tag("r"):  
            idea = self.hypothesis_generator.gen(self.trace)
            logger.log_object(idea, tag="hypothesis generation")
        return idea
        

    @measure_time
    def factor_construct(self, prev_out: dict[str, Any]):
        """
        Construct a variety of factors that depend on the hypothesis
        """
        with logger.tag("r"): 
            factor = self.factor_constructor.convert(prev_out["factor_propose"], self.trace)
            logger.log_object(factor.sub_tasks, tag="experiment generation")
        return factor

    @measure_time
    def factor_calculate(self, prev_out: dict[str, Any]):
        """
        Debug factors and calculate their values
        """
        with logger.tag("d"):  # develop
            factor = self.coder.develop(prev_out["factor_construct"])
            logger.log_object(factor.sub_workspace_list, tag="coder result")
        return factor
    

    @measure_time
    def factor_backtest(self, prev_out: dict[str, Any]):
        """
        Conduct Backtesting
        """
        with logger.tag("ef"):  # evaluate and feedback
            exp = self.runner.develop(prev_out["factor_calculate"])
            if exp is None:
                logger.error(f"Factor extraction failed.")
                raise FactorEmptyError("Factor extraction failed.")
            logger.log_object(exp, tag="runner result")
        return exp

    @measure_time
    def stop(self, prev_out: dict[str, Any]):
        exit(0)
