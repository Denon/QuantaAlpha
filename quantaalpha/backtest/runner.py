#!/usr/bin/env python3
"""
Backtest runner using Qlib: load factors (official/custom), compute custom factor values, train, backtest, evaluate.
Modes: official (Qlib DataLoader) or custom (expr_parser + function_lib).
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd
import yaml

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Backtest executor."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._qlib_initialized = False

    def _load_config(self) -> Dict:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded config: {self.config_path}")
        return config

    def _init_qlib(self):
        if self._qlib_initialized:
            return
        import os
        import qlib
        provider_uri = (
            os.environ.get('QLIB_DATA_DIR')
            or os.environ.get('QLIB_PROVIDER_URI')
            or self.config['data']['provider_uri']
        )
        provider_uri = os.path.expanduser(provider_uri)
        region = self.config['data'].get('region', 'cn')
        qlib.init(provider_uri=provider_uri, region=region)
        self._qlib_initialized = True
        logger.info(f"Qlib initialized: {provider_uri} (region={region})")

    def run(self,
            factor_source: Optional[str] = None,
            factor_json: Optional[List[str]] = None,
            experiment_name: Optional[str] = None,
            output_name: Optional[str] = None,
            skip_uncached: bool = False) -> Dict:
        """Run full backtest; returns metrics dict."""
        start_time_total = time.time()
        self._init_qlib()
        if factor_source:
            self.config['factor_source']['type'] = factor_source
        if factor_json:
            self.config['factor_source']['custom']['json_files'] = factor_json
        
        if output_name is None and factor_json:
            output_name = Path(factor_json[0]).stem

        exp_name = experiment_name or output_name or self.config['experiment']['name']
        rec_name = self.config['experiment']['recorder']

        print(f"\n{'='*50}")
        src = factor_json[0] if factor_json else exp_name
        print(f"Starting backtest: {src}")
        print(f"{'='*50}")

        factor_expressions, custom_factors = self._load_factors()
        print(f"[1/4] Loaded factors: Qlib {len(factor_expressions)}, custom {len(custom_factors)}")

        computed_factors = None
        per_factor_metrics = {}
        external_df = None
        if custom_factors:
            computed_factors = self._compute_custom_factors(custom_factors, skip_compute=skip_uncached)
            n_computed = len(computed_factors.columns) if computed_factors is not None and not computed_factors.empty else 0
            print(f"[2/4] Computed custom factors: {n_computed}")
            if computed_factors is not None and not computed_factors.empty:
                per_factor_metrics = self._compute_per_factor_ic(computed_factors)
                n_with_metrics = sum(1 for v in per_factor_metrics.values() if v)
                print(f"  Computed per-factor IC metrics: {n_with_metrics}/{n_computed}")
        else:
            logger.debug("[2/4] No custom factors, skip")

        # Load external data (if configured) and compute per-factor IC for it
        from .external_data import load_external_data
        external_df = load_external_data(self.config)
        if external_df is not None and not external_df.empty:
            ext_metrics = self._compute_per_factor_ic(external_df)
            # Only keep external metrics for columns that don't collide with
            # computed factors (colliding columns are dropped from the dataset below)
            ext_metrics = {k: v for k, v in ext_metrics.items()
                           if k not in per_factor_metrics}
            n_ext = sum(1 for v in ext_metrics.values() if v)
            per_factor_metrics.update(ext_metrics)
            print(f"  External data metrics: {n_ext}/{len(external_df.columns)} columns")

        dataset = self._create_dataset(factor_expressions, computed_factors, external_df)
        print("[3/4] Dataset created")

        metrics = self._train_and_backtest(dataset, exp_name, rec_name, output_name=output_name)
        total_time = time.time() - start_time_total
        self._print_results(metrics, total_time)
        metrics["per_factor_ic_metrics"] = per_factor_metrics

        ext_factor_count = len(external_df.columns) if external_df is not None else 0
        self._save_results(metrics, exp_name, factor_source or self.config['factor_source']['type'],
                          len(factor_expressions) + len(custom_factors) + ext_factor_count, total_time,
                          output_name=output_name)

        return metrics
    
    def _load_factors(self) -> Tuple[Dict[str, str], List[Dict]]:
        from .factor_loader import FactorLoader
        
        loader = FactorLoader(self.config)
        return loader.load_factors()
    
    def _compute_custom_factors(self, factors: List[Dict], skip_compute: bool = False) -> Optional[pd.DataFrame]:
        """Compute custom factors (expr_parser + function_lib); supports cache; loads stock data only when needed."""
        from .custom_factor_calculator import CustomFactorCalculator
        from pathlib import Path

        llm_config = self.config.get('llm', {})
        cache_dir = llm_config.get('cache_dir')
        if cache_dir:
            cache_dir = Path(cache_dir)
        auto_extract = llm_config.get('auto_extract_cache', True)
        calculator = CustomFactorCalculator(
            data_df=None,
            cache_dir=cache_dir,
            auto_extract_cache=auto_extract,
            config=self.config,
        )
        use_cache = llm_config.get('cache_results', True)
        result_df = calculator.calculate_factors_batch(factors, use_cache=use_cache, skip_compute=skip_compute)
        if result_df is None:
            logger.error("Factor computation returned None")
            return None
        if not isinstance(result_df, pd.DataFrame):
            logger.error(f"Factor computation returned wrong type: {type(result_df)}")
            return None
        
        if result_df.empty:
            logger.error("Factor computation returned empty DataFrame")
            return None
        
        if not isinstance(result_df.index, pd.MultiIndex):
            logger.warning("Factor data index is not MultiIndex, attempting fix...")
        logger.debug(f"  Factor computation done: {len(result_df.columns)} factors, {len(result_df)} rows")
        
        return result_df

    def _compute_per_factor_ic(self, computed_factors: pd.DataFrame) -> dict:
        """Compute per-factor IC metrics for each computed factor column.

        Returns dict mapping factor_name -> {factor_metrics: {...}, metric_context: {...}}.
        """
        from quantaalpha.backtest.ic_metrics import compute_factor_metrics, MetricContext

        data_config = self.config.get("data", {})
        dataset_config = self.config.get("dataset", {})
        label_expr = dataset_config.get("label", "Ref($close, -2) / Ref($close, -1) - 1")

        label_df = self._compute_label(label_expr)
        if label_df is None or label_df.empty:
            logger.warning("Cannot compute per-factor IC: label data is empty")
            return {}

        # Normalize both label and factor indices to canonical (datetime, instrument)
        # so intersection works regardless of source (Qlib returns instrument,datetime).
        if isinstance(label_df.index, pd.MultiIndex) and label_df.index.names == ["instrument", "datetime"]:
            label_df = label_df.swaplevel().sort_index()
        if isinstance(computed_factors.index, pd.MultiIndex) and computed_factors.index.names == ["instrument", "datetime"]:
            computed_factors = computed_factors.swaplevel().sort_index()

        ctx = MetricContext(
            provider_uri=data_config.get("provider_uri", ""),
            market=data_config.get("market", ""),
            start_time=data_config.get("start_time", ""),
            end_time=data_config.get("end_time", ""),
            label_expr=label_expr,
        )

        result = {}
        for col in computed_factors.columns:
            factor_series = computed_factors[col]
            try:
                metrics_result = compute_factor_metrics(
                    factor_series, label_df["LABEL0"], metric_context=ctx
                )
                result[col] = metrics_result
            except Exception as e:
                logger.debug(f"Per-factor IC failed [{col}]: {e}")

        return result

    def _create_dataset(self,
                       factor_expressions: Dict[str, str],
                       computed_factors: Optional[pd.DataFrame] = None,
                       external_df: Optional[pd.DataFrame] = None):
        """Create Qlib dataset (QlibDataLoader or precomputed factors + StaticDataLoader)."""
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        
        data_config = self.config['data']
        dataset_config = self.config['dataset']
        
        has_computed_factors = False
        if computed_factors is not None:
            if isinstance(computed_factors, pd.DataFrame):
                if len(computed_factors) > 0 and len(computed_factors.columns) > 0:
                    has_computed_factors = True
                    logger.debug(f"  Precomputed factors: {len(computed_factors.columns)} factors, {len(computed_factors)} rows")
                else:
                    logger.warning(f"  Precomputed factor DataFrame is empty: {computed_factors.shape}")
            else:
                logger.warning(f"  Precomputed factor type invalid: {type(computed_factors)}")
        
        # Also check for external data
        has_external = (external_df is not None
                        and isinstance(external_df, pd.DataFrame)
                        and not external_df.empty)
        if has_external:
            logger.debug(f"  External data: {len(external_df.columns)} columns")

        # Prefer custom factor mode when computed factors or external data exist
        if has_computed_factors or has_external:
            logger.debug("  Using custom factor mode (precomputed)")
            return self._create_dataset_with_computed_factors(
                factor_expressions, computed_factors, external_df
            )
        
        # Qlib-only factor mode
        expressions = list(factor_expressions.values())
        names = list(factor_expressions.keys())
        
        if not expressions:
            raise ValueError("No factor expressions available. If using custom factors, ensure factor computation succeeded.")
        
        handler_config = {
            'start_time': data_config['start_time'],
            'end_time': data_config['end_time'],
            'instruments': data_config['market'],
            'data_loader': {
                'class': 'QlibDataLoader',
                'module_path': 'qlib.contrib.data.loader',
                'kwargs': {
                    'config': {
                        'feature': (expressions, names),
                        'label': ([dataset_config['label']], ['LABEL0'])
                    }
                }
            },
            'learn_processors': dataset_config['learn_processors'],
            'infer_processors': dataset_config['infer_processors']
        }
        
        dataset = DatasetH(
            handler=DataHandlerLP(**handler_config),
            segments=dataset_config['segments']
        )
        
        logger.debug(f"  Qlib mode: {len(expressions)} factors, train={dataset_config['segments']['train']}")
        
        return dataset
    
    def _create_dataset_with_computed_factors(self,
                                              factor_expressions: Dict[str, str],
                                              computed_factors: pd.DataFrame,
                                              external_df: Optional[pd.DataFrame] = None):
        """Create dataset from precomputed factors: compute label, merge with factors, delegate to
        the shared `build_precomputed_dataset` for alignment, preprocessing, and DatasetH construction."""
        from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset

        dataset_config = self.config['dataset']

        logger.debug(f"  Computed factor count: {len(computed_factors.columns) if computed_factors is not None else 0}")
        label_expr = dataset_config['label']
        label_df = self._compute_label(label_expr)

        all_feature_dfs = []
        if computed_factors is not None and not computed_factors.empty:
            all_feature_dfs.append(computed_factors)
        if factor_expressions:
            logger.debug(f"  Loading {len(factor_expressions)} Qlib-compatible factors")
            qlib_factors = self._load_qlib_factors(factor_expressions)
            if qlib_factors is not None and not qlib_factors.empty:
                all_feature_dfs.append(qlib_factors)
        if external_df is not None and not external_df.empty:
            existing_cols = set()
            for df in all_feature_dfs:
                existing_cols.update(df.columns)
            ext_to_add = [c for c in external_df.columns if c not in existing_cols]
            if len(ext_to_add) < len(external_df.columns):
                dropped = set(external_df.columns) - set(ext_to_add)
                logger.warning(f"Dropping external columns that conflict with computed factors: {dropped}")
            all_feature_dfs.append(external_df[ext_to_add])

        features_df = pd.concat(all_feature_dfs, axis=1)
        features_df = features_df.loc[:, ~features_df.columns.duplicated()]
        logger.debug(f"  Total factor count: {len(features_df.columns)}")

        dataset = build_precomputed_dataset(
            features_df=features_df,
            label_df=label_df,
            segments=dataset_config["segments"],
        )

        logger.debug(f"  Custom factor mode: {len(features_df.columns)} factors, train={dataset_config['segments']['train']}")

        return dataset
    
    def _apply_backtest_window(
        self, train: tuple[str, str], valid: tuple[str, str], test: tuple[str, str]
    ) -> None:
        """Mutate this runner's config segments and backtest range for a single fold.

        The walk-forward orchestrator is responsible for deep-copying the config
        baseline before each fold so mutations do not leak.
        """
        self.config["dataset"]["segments"] = {
            "train": [train[0], train[1]],
            "valid": [valid[0], valid[1]],
            "test": [test[0], test[1]],
        }
        self.config["backtest"]["backtest"]["start_time"] = test[0]
        self.config["backtest"]["backtest"]["end_time"] = test[1]

    def _create_dataset_from_feature_frame(self, features_df: pd.DataFrame):
        """Build a Qlib dataset from a pre-selected feature frame and the label defined in config."""
        label_df = self._compute_label(self.config["dataset"]["label"])
        from quantaalpha.backtest.precomputed_dataset import build_precomputed_dataset

        return build_precomputed_dataset(
            features_df=features_df,
            label_df=label_df,
            segments=self.config["dataset"]["segments"],
        )

    def run_feature_frame(
        self,
        features_df: pd.DataFrame,
        exp_name: str,
        rec_name: str,
        output_name: str | None = None,
    ) -> dict:
        """Run a backtest end-to-end from a pre-loaded feature DataFrame.

        Used by the walk-forward orchestrator to execute a single fold after
        factor selection has been applied.
        """
        dataset = self._create_dataset_from_feature_frame(features_df)
        return self._train_and_backtest(dataset, exp_name, rec_name, output_name=output_name)

    def prepare_feature_frame(
        self, custom_factors: list[dict] | None = None, skip_uncached: bool = False
    ) -> pd.DataFrame:
        """Load and concatenate all candidate factor features once.

        Covers Qlib expression factors, custom computed factors, and external data.
        Returns a single DataFrame with unique column names suitable for per-fold
        factor selection. All frames are normalized to (instrument, datetime) index
        to match typical Qlib output.
        """
        from quantaalpha.backtest.precomputed_dataset import _normalize_multiindex

        factor_expressions, loaded_custom = self._load_factors()
        custom_to_compute = custom_factors if custom_factors is not None else loaded_custom
        frames = []
        if factor_expressions:
            qlib_features = self._load_qlib_factors(factor_expressions)
            if qlib_features is not None and not qlib_features.empty:
                frames.append(qlib_features)
        if custom_to_compute:
            computed = self._compute_custom_factors(custom_to_compute, skip_compute=skip_uncached)
            if computed is not None and not computed.empty:
                frames.append(computed)
        from quantaalpha.backtest.external_data import load_external_data

        external_df = load_external_data(self.config)
        if external_df is not None and not external_df.empty:
            frames.append(external_df)
        if not frames:
            raise ValueError("No candidate factor features available")

        # Normalize all frames to a consistent (instrument, datetime) index order
        normalized = [_normalize_multiindex(f, f"candidate_{i}") for i, f in enumerate(frames)]
        return pd.concat(normalized, axis=1).loc[:, lambda df: ~df.columns.duplicated()]

    def _compute_label(self, label_expr: str) -> pd.DataFrame:
        """Compute label using Qlib (label requires look-ahead)."""
        from qlib.data import D

        data_config = self.config['data']

        logger.debug(f"  Label expr: {label_expr}")

        stock_list = D.instruments(data_config['market'])

        label_df = D.features(
            stock_list,
            [label_expr],
            start_time=data_config['start_time'],
            end_time=data_config['end_time'],
            freq='day'
        )

        label_df.columns = ['LABEL0']

        logger.debug(f"  Label rows: {len(label_df)}")

        return label_df
    
    def _load_qlib_factors(self, factor_expressions: Dict[str, str]) -> Optional[pd.DataFrame]:
        """Load Qlib-compatible factors."""
        from qlib.data import D
        
        data_config = self.config['data']
        
        try:
            stock_list = D.instruments(data_config['market'])
            
            expressions = list(factor_expressions.values())
            names = list(factor_expressions.keys())
            
            df = D.features(
                stock_list,
                expressions,
                start_time=data_config['start_time'],
                end_time=data_config['end_time'],
                freq='day'
            )
            
            df.columns = names
            return df
        except Exception as e:
            logger.warning(f"Failed to load Qlib factors: {e}")
            return None
    
    def _train_and_backtest(self, dataset, exp_name: str, rec_name: str, output_name: Optional[str] = None) -> Dict:
        """Train model and run backtest."""
        from qlib.contrib.model.gbdt import LGBModel
        from qlib.data import D
        from qlib.workflow import R
        from qlib.workflow.record_temp import SignalRecord, SigAnaRecord
        from qlib.backtest import backtest as qlib_backtest
        from qlib.contrib.evaluate import risk_analysis
        
        model_config = self.config['model']
        backtest_config = self.config['backtest']['backtest']
        strategy_config = self.config['backtest']['strategy']
        
        metrics = {}
        
        with R.start(experiment_name=exp_name, recorder_name=rec_name):
            # Train model
            train_start = time.time()
            
            if model_config['type'] == 'lgb':
                model = LGBModel(**model_config['params'])
            else:
                raise ValueError(f"Unsupported model type: {model_config['type']}")
            
            model.fit(dataset)
            print(f"[4/4] Train LightGBM done ({time.time()-train_start:.1f}s)")
            
            # Generate prediction
            pred = model.predict(dataset)
            logger.debug(f"  Pred shape: {pred.shape}")
            
            # Save prediction
            sr = SignalRecord(recorder=R.get_recorder(), model=model, dataset=dataset)
            sr.generate()
            
            # Compute IC metrics
            try:
                sar = SigAnaRecord(recorder=R.get_recorder(), ana_long_short=False, ann_scaler=252)
                sar.generate()
                
                recorder = R.get_recorder()
                try:
                    ic_series = recorder.load_object("sig_analysis/ic.pkl")
                    ric_series = recorder.load_object("sig_analysis/ric.pkl")
                    
                    if isinstance(ic_series, pd.Series) and len(ic_series) > 0:
                        metrics['IC'] = float(ic_series.mean())
                        metrics['ICIR'] = float(ic_series.mean() / ic_series.std()) if ic_series.std() > 0 else 0.0
                    
                    if isinstance(ric_series, pd.Series) and len(ric_series) > 0:
                        metrics['Rank IC'] = float(ric_series.mean())
                        metrics['Rank ICIR'] = float(ric_series.mean() / ric_series.std()) if ric_series.std() > 0 else 0.0
                    
                    print(f"  IC={metrics.get('IC', 0):.6f}, ICIR={metrics.get('ICIR', 0):.6f}, "
                          f"Rank IC={metrics.get('Rank IC', 0):.6f}, Rank ICIR={metrics.get('Rank ICIR', 0):.6f}")
                except Exception as e:
                    logger.warning(f"Could not read IC result: {e}")
            except Exception as e:
                logger.warning(f"IC analysis failed: {e}")
            # Portfolio backtest
            try:
                bt_start = time.time()
                
                market = self.config['data']['market']
                instruments = D.instruments(market)
                stock_list = D.list_instruments(
                    instruments,
                    start_time=backtest_config['start_time'],
                    end_time=backtest_config['end_time'],
                    as_list=True
                )
                logger.debug(f"  Stock count: {len(stock_list)}")
                if len(stock_list) < 10:
                    logger.warning(f"Stock pool too small ({len(stock_list)}), results may be unreliable")
                # Filter invalid price signals
                try:
                    price_data = D.features(
                        stock_list,
                        ['$close'],
                        start_time=backtest_config['start_time'],
                        end_time=backtest_config['end_time'],
                        freq='day'
                    )
                    invalid_mask = (price_data['$close'] == 0) | (price_data['$close'].isna())
                    invalid_count = invalid_mask.sum()
                    
                    if invalid_count > 0:
                        logger.debug(f"  Found {invalid_count} zero/NaN price records")
                        if isinstance(pred, pd.Series):
                            invalid_indices = invalid_mask[invalid_mask].index
                            invalid_set = set()
                            for idx in invalid_indices:
                                instrument, datetime = idx
                                invalid_set.add((datetime, instrument))
                            
                            filtered_count = 0
                            for idx in pred.index:
                                if idx in invalid_set:
                                    pred.loc[idx] = np.nan
                                    filtered_count += 1
                            
                            if filtered_count > 0:
                                logger.debug(f"  Filtered {filtered_count} invalid price signals")
                except Exception as filter_err:
                    logger.warning(f"Price filter failed: {filter_err}")
                
                portfolio_metric_dict, indicator_dict = qlib_backtest(
                    executor={
                        "class": "SimulatorExecutor",
                        "module_path": "qlib.backtest.executor",
                        "kwargs": {
                            "time_per_step": "day",
                            "generate_portfolio_metrics": True,
                            "verbose": False,
                            "indicator_config": {"show_indicator": False}
                        }
                    },
                    strategy={
                        "class": strategy_config['class'],
                        "module_path": strategy_config['module_path'],
                        "kwargs": {
                            "signal": pred,
                            "topk": strategy_config['kwargs']['topk'],
                            "n_drop": strategy_config['kwargs']['n_drop']
                        }
                    },
                    start_time=backtest_config['start_time'],
                    end_time=backtest_config['end_time'],
                    account=backtest_config['account'],
                    benchmark=backtest_config['benchmark'],
                    exchange_kwargs={
                        "codes": stock_list,
                        **backtest_config['exchange_kwargs']
                    }
                )
                
                print(f"  Portfolio backtest done ({time.time()-bt_start:.1f}s)")
                # Extract portfolio metrics
                if portfolio_metric_dict and "1day" in portfolio_metric_dict:
                    report_df, positions_df = portfolio_metric_dict["1day"]
                    
                    if isinstance(report_df, pd.DataFrame) and 'return' in report_df.columns:
                        portfolio_return = report_df['return'].replace([np.inf, -np.inf], np.nan).fillna(0)
                        bench_return = report_df['bench'].replace([np.inf, -np.inf], np.nan).fillna(0) if 'bench' in report_df.columns else 0
                        cost = report_df['cost'].replace([np.inf, -np.inf], np.nan).fillna(0) if 'cost' in report_df.columns else 0
                        
                        excess_return_with_cost = portfolio_return - bench_return - cost
                        excess_return_with_cost = excess_return_with_cost.dropna()
                        
                        if len(excess_return_with_cost) > 0:
                            try:
                                daily_df = report_df.copy()
                                daily_df['excess_return'] = excess_return_with_cost
                                
                                output_dir = Path(self.config['experiment'].get('output_dir', './backtest_v2_results'))
                                output_dir.mkdir(parents=True, exist_ok=True)
                                
                                file_prefix = output_name if output_name else exp_name
                                csv_path = output_dir / f"{file_prefix}_cumulative_excess.csv"
                                save_df = daily_df[['excess_return']].copy()
                                save_df.columns = ['daily_excess_return']
                                save_df['cumulative_excess_return'] = save_df['daily_excess_return'].cumsum()
                                
                                save_df.index.name = 'date'
                                save_df.to_csv(csv_path)
                                logger.debug(f"  Daily excess return saved: {csv_path}")
                            except Exception as csv_err:
                                logger.warning(f"Failed to save daily CSV: {csv_err}")

                            analysis = risk_analysis(excess_return_with_cost)
                            
                            if isinstance(analysis, pd.DataFrame):
                                analysis = analysis['risk'] if 'risk' in analysis.columns else analysis.iloc[:, 0]
                            
                            ann_ret = float(analysis.get('annualized_return', 0))
                            info_ratio = float(analysis.get('information_ratio', 0))
                            max_dd = float(analysis.get('max_drawdown', 0))
                            
                            if not np.isnan(ann_ret) and not np.isinf(ann_ret):
                                metrics['annualized_return'] = ann_ret
                            if not np.isnan(info_ratio) and not np.isinf(info_ratio):
                                metrics['information_ratio'] = info_ratio
                            if not np.isnan(max_dd) and not np.isinf(max_dd):
                                metrics['max_drawdown'] = max_dd
                            
                            if max_dd != 0 and not np.isnan(ann_ret) and not np.isinf(ann_ret):
                                calmar = ann_ret / abs(max_dd)
                                if not np.isnan(calmar) and not np.isinf(calmar):
                                    metrics['calmar_ratio'] = calmar
                            
            except Exception as e:
                logger.warning(f"Portfolio backtest failed: {e}")
                import traceback
                traceback.print_exc()
        
        return metrics
    
    def _print_results(self, metrics: Dict, total_time: float):
        """Print result summary."""
        def _f(val, fmt='.6f'):
            return format(val, fmt) if isinstance(val, (int, float)) else 'N/A'

        print(f"\n{'='*50}")
        print("Backtest Results")
        print(f"{'='*50}")
        print("[IC Metrics]")
        print(f"  IC: {_f(metrics.get('IC'))}  ICIR: {_f(metrics.get('ICIR'))}")
        print(f"  Rank IC: {_f(metrics.get('Rank IC'))}  Rank ICIR: {_f(metrics.get('Rank ICIR'))}")
        print("[Strategy Metrics]")
        print(f"  Ann. Return: {_f(metrics.get('annualized_return'), '.4f')}  Max DD: {_f(metrics.get('max_drawdown'), '.4f')}")
        print(f"  Info Ratio: {_f(metrics.get('information_ratio'), '.4f')}  Calmar: {_f(metrics.get('calmar_ratio'), '.4f')}")
        print(f"Total time: {total_time:.1f}s")
        print(f"{'='*50}")
    
    def _save_results(self, metrics: Dict, exp_name: str, 
                     factor_source: str, num_factors: int, elapsed: float,
                     output_name: Optional[str] = None):
        """Save results."""
        output_dir = Path(self.config['experiment'].get('output_dir', './backtest_v2_results'))
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_name:
            output_file = f"{output_name}_backtest_metrics.json"
        else:
            output_file = self.config['experiment']['output_metrics_file']
        output_path = output_dir / output_file
        
        result_data = {
            "experiment_name": exp_name,
            "factor_source": factor_source,
            "num_factors": num_factors,
            "metrics": metrics,
            "config": {
                "data_range": f"{self.config['data']['start_time']} ~ {self.config['data']['end_time']}",
                "test_range": f"{self.config['dataset']['segments']['test'][0]} ~ {self.config['dataset']['segments']['test'][1]}",
                "backtest_range": f"{self.config['backtest']['backtest']['start_time']} ~ {self.config['backtest']['backtest']['end_time']}",
                "market": self.config['data']['market'],
                "benchmark": self.config['backtest']['backtest']['benchmark']
            },
            "elapsed_seconds": elapsed
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        print(f"Results saved: {output_path}")
        summary_file = output_dir / "batch_summary.json"
        summary_data = []
        if summary_file.exists():
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
            except:
                summary_data = []
        
        ann_ret = metrics.get('annualized_return')
        mdd = metrics.get('max_drawdown')
        calmar_ratio = None
        if ann_ret is not None and mdd is not None and mdd != 0:
            calmar_ratio = ann_ret / abs(mdd)
        
        summary_entry = {
            "name": output_name or exp_name,
            "num_factors": num_factors,
            "IC": metrics.get('IC'),
            "ICIR": metrics.get('ICIR'),
            "Rank_IC": metrics.get('Rank IC'),
            "Rank_ICIR": metrics.get('Rank ICIR'),
            "annualized_return": ann_ret,
            "information_ratio": metrics.get('information_ratio'),
            "max_drawdown": mdd,
            "calmar_ratio": calmar_ratio,
            "elapsed_seconds": elapsed
        }
        summary_data.append(summary_entry)
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Appended to summary: {summary_file}")
