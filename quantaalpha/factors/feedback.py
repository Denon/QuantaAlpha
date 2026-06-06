import json
from pathlib import Path

import pandas as pd
from jinja2 import Environment, StrictUndefined

from quantaalpha.core.experiment import Experiment
from quantaalpha.core.prompts import Prompts
from quantaalpha.core.proposal import (
    Hypothesis,
    HypothesisExperiment2Feedback,
    HypothesisFeedback,
    Trace,
)
from quantaalpha.log import logger
from quantaalpha.llm.client import APIBackend, robust_json_parse
from quantaalpha.utils import convert2bool

# Max retries for JSON parsing
MAX_JSON_PARSE_RETRIES = 3

base_feedback_prompts = Prompts(file_path=Path(__file__).parent / "prompts" / "prompts.yaml")
DIRNAME = Path(__file__).absolute().resolve().parent


def process_results(current_result, sota_result):
    # Convert the results to dataframes
    current_df = pd.DataFrame(current_result)
    
    # Handle case where sota_result might be None or empty
    if sota_result is None or (isinstance(sota_result, pd.DataFrame) and sota_result.empty):
        # If no SOTA result, return only current result
        current_df.index.name = "metric"
        if "0" in current_df.columns:
            current_df.rename(columns={"0": "Current Result"}, inplace=True)
        elif len(current_df.columns) > 0:
            # Use first column if "0" doesn't exist
            first_col = current_df.columns[0]
            current_df.rename(columns={first_col: "Current Result"}, inplace=True)
        
        # Select important metrics for comparison
        important_metrics = [
            "1day.excess_return_without_cost.max_drawdown",
            "1day.excess_return_without_cost.information_ratio",
            "1day.excess_return_without_cost.annualized_return",
            "IC",
        ]
        
        # Filter the DataFrame to retain only the important metrics that exist
        available_metrics = [m for m in important_metrics if m in current_df.index]
        if available_metrics:
            filtered_df = current_df.loc[available_metrics]
        else:
            filtered_df = current_df
        
        return filtered_df.to_string()
    
    sota_df = pd.DataFrame(sota_result)

    # Set the metric as the index
    current_df.index.name = "metric"
    sota_df.index.name = "metric"

    # Rename the value column to reflect the result type
    # Handle case where column "0" might not exist
    if "0" in current_df.columns:
        current_df.rename(columns={"0": "Current Result"}, inplace=True)
    elif len(current_df.columns) > 0:
        first_col = current_df.columns[0]
        current_df.rename(columns={first_col: "Current Result"}, inplace=True)
    else:
        # If no columns, create a dummy column
        current_df["Current Result"] = 0
    
    if "0" in sota_df.columns:
        sota_df.rename(columns={"0": "SOTA Result"}, inplace=True)
    elif len(sota_df.columns) > 0:
        first_col = sota_df.columns[0]
        sota_df.rename(columns={first_col: "SOTA Result"}, inplace=True)
    else:
        # If no columns, create a dummy column
        sota_df["SOTA Result"] = 0

    # Combine the dataframes on the Metric index
    combined_df = pd.concat([current_df, sota_df], axis=1)

    # Select important metrics for comparison
    important_metrics = [
        "1day.excess_return_without_cost.max_drawdown",
        "1day.excess_return_without_cost.information_ratio",
        "1day.excess_return_without_cost.annualized_return",
        "IC",
    ]

    # Filter the combined DataFrame to retain only the important metrics that exist
    available_metrics = [m for m in important_metrics if m in combined_df.index]
    if available_metrics:
        filtered_combined_df = combined_df.loc[available_metrics]
    else:
        filtered_combined_df = combined_df

    # Check if both columns exist before comparing
    if "Current Result" in filtered_combined_df.columns and "SOTA Result" in filtered_combined_df.columns:
        filtered_combined_df[
            "Bigger columns name (Didn't consider the direction of the metric, you should judge it by yourself that bigger is better or smaller is better)"
        ] = filtered_combined_df.apply(
                lambda row: "Current Result" if pd.notna(row["Current Result"]) and pd.notna(row["SOTA Result"]) and row["Current Result"] > row["SOTA Result"] else "SOTA Result", axis=1
        )
    elif "Current Result" in filtered_combined_df.columns:
        # Only current result available
        filtered_combined_df[
            "Bigger columns name (Didn't consider the direction of the metric, you should judge it by yourself that bigger is better or smaller is better)"
        ] = "Current Result"
    elif "SOTA Result" in filtered_combined_df.columns:
        # Only SOTA result available
        filtered_combined_df[
            "Bigger columns name (Didn't consider the direction of the metric, you should judge it by yourself that bigger is better or smaller is better)"
        ] = "SOTA Result"

    return filtered_combined_df.to_string()


def build_regime_table(exp, regime_map) -> str | None:
    """Build per-regime IC performance table from experiment workspace data.

    Loads factor values from workspace result files, computes daily IC using
    Qlib labels, groups daily IC by regime using the monthly regime map, and
    returns a side-by-side Markdown table.

    Args:
        exp: Experiment with sub_workspace_list containing executed factor data.
        regime_map: DataFrame from load_regime_map() with month_start/month_end/regime columns.

    Returns:
        Formatted Markdown string with per-regime IC and n_trading_days, or None
        if computation fails (missing data, Qlib not initialized, etc.).
    """
    if regime_map is None:
        return None

    MIN_DAYS = 20

    try:
        import qlib
        from qlib.data import D
        from quantaalpha.backtest.ic_metrics import compute_daily_ic
    except ImportError as e:
        logger.warning(f"Cannot import Qlib/IC dependencies for regime table: {e}")
        return None

    try:
        # Collect factor values from workspace result files
        factor_data = {}  # factor_name -> factor_series
        for ws in exp.sub_workspace_list:
            h5_path = ws.workspace_path / "result.h5"
            if not h5_path.exists():
                continue
            try:
                df = pd.read_hdf(h5_path)
                if isinstance(df, pd.DataFrame):
                    if df.shape[1] == 1:
                        series = df.iloc[:, 0]
                    else:
                        series = df.iloc[:, 0]
                elif isinstance(df, pd.Series):
                    series = df
                else:
                    continue

                if series.empty:
                    continue

                name = getattr(ws.target_task, 'factor_name', f'factor_{len(factor_data)}')
                # Ensure datetime is in index
                if not isinstance(series.index, pd.MultiIndex):
                    if hasattr(series.index, 'name') and series.index.name == 'datetime':
                        # Single-level datetime index isn't usable with compute_daily_ic
                        continue

                factor_data[name] = series
            except Exception as e:
                logger.debug(f"Skipping factor workspace {ws.workspace_path}: {e}")
                continue

        if not factor_data:
            logger.info("No factor workspace result files found; cannot compute per-regime IC")
            return None

        # Determine date range from factor data
        all_dates = []
        for series in factor_data.values():
            if isinstance(series.index, pd.MultiIndex):
                dt_level = series.index.get_level_values('datetime')
            else:
                dt_level = series.index
            all_dates.extend(pd.to_datetime(dt_level).tolist())

        if not all_dates:
            return None

        result_start = min(all_dates)
        result_end = max(all_dates)

        # Load label data from Qlib
        try:
            import os

            # Ensure Qlib is initialized (may not be if running in main process
            # while backtest ran in subprocess). qlib.init() is safe to call twice.
            provider_uri = os.environ.get(
                "QLIB_PROVIDER_URI",
                os.path.expanduser("~/.qlib/qlib_data/cn_data"),
            )
            region = os.environ.get("QLIB_REGION", "cn")
            qlib.init(provider_uri=provider_uri, region=region)

            instruments = D.instruments('all')
            label_expr = 'Ref($close, -2)/Ref($close, -1) - 1'
            label_df = D.features(
                instruments,
                [label_expr],
                start_time=result_start.strftime('%Y-%m-%d') if hasattr(result_start, 'strftime') else str(result_start)[:10],
                end_time=result_end.strftime('%Y-%m-%d') if hasattr(result_end, 'strftime') else str(result_end)[:10],
            )
            label_series = label_df.iloc[:, 0]
        except Exception as e:
            logger.warning(f"Failed to load Qlib labels for regime table: {e}")
            return None

        # Map each date to a regime label
        regime_map_copy = regime_map.copy()
        regime_map_copy['month_start'] = pd.to_datetime(regime_map_copy['month_start'])
        regime_map_copy['month_end'] = pd.to_datetime(regime_map_copy['month_end'])

        # Get unique regime labels
        regime_labels = sorted(regime_map_copy['regime'].dropna().unique())
        if not regime_labels:
            return None

        # Compute per-regime IC for each factor
        regime_metrics = {}  # regime -> {factor_name: mean_ic}
        regime_day_counts = {}  # regime -> int

        # Build date-to-regime lookup
        date_regime_map = {}
        for _, row in regime_map_copy.iterrows():
            regime = row['regime']
            if pd.isna(regime):
                continue
            # Each date in the month gets this regime
            ms = row['month_start']
            me = row['month_end']
            if isinstance(ms, pd.Timestamp) and isinstance(me, pd.Timestamp):
                dates_in_month = pd.date_range(ms, me, freq='B')
                for d in dates_in_month:
                    date_regime_map[d.date()] = regime

        # Compute daily IC for each factor
        for fname, fseries in factor_data.items():
            try:
                daily_pearson, daily_rank, n_days, n_obs = compute_daily_ic(fseries, label_series)
                if daily_pearson.empty:
                    continue

                # Group daily IC by regime
                for dt, ic_val in daily_pearson.items():
                    dt_date = dt.date() if hasattr(dt, 'date') else pd.Timestamp(dt).date()
                    regime = date_regime_map.get(dt_date)
                    if regime is None:
                        continue
                    if regime not in regime_metrics:
                        regime_metrics[regime] = {}
                        regime_day_counts[regime] = 0
                    if fname not in regime_metrics[regime]:
                        regime_metrics[regime][fname] = []
                    regime_metrics[regime][fname].append(ic_val)
                    regime_day_counts[regime] += 1

            except Exception as e:
                logger.debug(f"Failed to compute daily IC for factor {fname}: {e}")
                continue

        if not regime_metrics:
            logger.info("No regime metrics computed (no overlap between IC dates and regime map)")
            return None

        # For each regime, compute mean IC across all factors (simple average)
        # Build table rows
        regimes_in_table = []
        for regime in regime_labels:
            if regime not in regime_metrics:
                continue
            regimes_in_table.append(regime)

        if not regimes_in_table:
            return None

        # Build side-by-side table
        header = "| metric | " + " | ".join(regimes_in_table) + " |"
        sep = "|---|" + "|".join(["---|"] * len(regimes_in_table))

        ic_row_parts = []
        ann_ret_row_parts = []
        ir_row_parts = []
        dd_row_parts = []
        ndays_row_parts = []

        for regime in regimes_in_table:
            n_days = sum(1 for d, r in date_regime_map.items() if r == regime)
            ndays_row_parts.append(f" {n_days} ")

            # Compute mean IC for this regime across all factors
            all_ics = []
            for fname, ics in regime_metrics[regime].items():
                all_ics.extend(ics)
            mean_ic = sum(all_ics) / len(all_ics) if all_ics else float('nan')

            ic_row_parts.append(f" {mean_ic: .4f} " if not pd.isna(mean_ic) else " N/A ")
            # For v1, other metrics are not computed from raw data
            ann_ret_row_parts.append(" — ")
            ir_row_parts.append(" — ")
            dd_row_parts.append(" — ")

        lines = [header, sep,
                 "| IC |" + "|".join(ic_row_parts) + "|",
                 "| ann_return |" + "|".join(ann_ret_row_parts) + "|",
                 "| IR |" + "|".join(ir_row_parts) + "|",
                 "| max_dd |" + "|".join(dd_row_parts) + "|",
                 "| n_trading_days |" + "|".join(ndays_row_parts) + "|"]

        # Mark low-sample regimes
        low_sample_notes = []
        for regime in regimes_in_table:
            n = sum(1 for d, r in date_regime_map.items() if r == regime)
            if n < MIN_DAYS:
                low_sample_notes.append(regime)

        if low_sample_notes:
            lines.append("")
            lines.append(f"*low sample (<{MIN_DAYS} trading days): " + ", ".join(low_sample_notes))

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Failed to build regime table: {e}")
        return None


class QlibFactorHypothesisExperiment2Feedback(HypothesisExperiment2Feedback):
    def generate_feedback(self, exp: Experiment, hypothesis: Hypothesis, trace: Trace) -> HypothesisFeedback:
        """
        Generate feedback for the given experiment and hypothesis.

        Args:
            exp (QlibFactorExperiment): The experiment to generate feedback for.
            hypothesis (QlibFactorHypothesis): The hypothesis to generate feedback for.
            trace (Trace): The trace of the experiment.

        Returns:
            Any: The feedback generated for the given experiment and hypothesis.
        """
        logger.info("Generating feedback...")
        hypothesis_text = hypothesis.hypothesis
        current_result = exp.result
        tasks_factors = [task.get_task_information_and_implementation_result() for task in exp.sub_tasks]
        # Safely get SOTA result, handle case where based_experiments might be empty or result is None
        sota_result = None
        if exp.based_experiments and len(exp.based_experiments) > 0:
            sota_result = exp.based_experiments[-1].result

        # Process the results to filter important metrics
        combined_result = process_results(current_result, sota_result)

        # Generate the system prompt
        sys_prompt = (
            Environment(undefined=StrictUndefined)
            .from_string(base_feedback_prompts["factor_feedback_generation"]["system"])
            .render(scenario=self.scen.get_scenario_all_desc())
        )

        # Generate the user prompt
        usr_prompt = (
            Environment(undefined=StrictUndefined)
            .from_string(base_feedback_prompts["factor_feedback_generation"]["user"])
            .render(
                hypothesis_text=hypothesis_text,
                task_details=tasks_factors,
                combined_result=combined_result,
                regime_table=None,
            )
        )

        # Call the APIBackend to generate the response for hypothesis feedback with retry
        response_json = None
        last_error = None

        for attempt in range(MAX_JSON_PARSE_RETRIES):
            try:
                response = APIBackend().build_messages_and_create_chat_completion(
                    user_prompt=usr_prompt,
                    system_prompt=sys_prompt,
                    json_mode=True,
                )
                # Parse the JSON response using robust parser
                response_json = robust_json_parse(response)
                break
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(f"[QuantaAlpha] JSON parse failed (attempt {attempt + 1}/{MAX_JSON_PARSE_RETRIES}): {e}")
                if attempt < MAX_JSON_PARSE_RETRIES - 1:
                    logger.info("[QuantaAlpha] Re-requesting LLM...")
                continue

        if response_json is None:
            logger.error(f"[QuantaAlpha] JSON parse still failed after {MAX_JSON_PARSE_RETRIES} attempts")
            return HypothesisFeedback(
                observations="JSON parse failed; could not extract feedback",
                hypothesis_evaluation="Unable to evaluate",
                new_hypothesis="",
                reason=f"JSON parse error: {last_error}",
                decision=False,
            )

        # Extract fields from JSON response
        observations = response_json.get("Observations", "No observations provided")
        hypothesis_evaluation = response_json.get("Feedback for Hypothesis", "No feedback provided")
        new_hypothesis = response_json.get("New Hypothesis", "No new hypothesis provided")
        reason = response_json.get("Reasoning", "No reasoning provided")
        decision = convert2bool(response_json.get("Replace Best Result", "no"))

        return HypothesisFeedback(
            observations=observations,
            hypothesis_evaluation=hypothesis_evaluation,
            new_hypothesis=new_hypothesis,
            reason=reason,
            decision=decision,
        )



qa_feedback_prompts = Prompts(file_path=Path(__file__).parent / "prompts" / "prompts.yaml")
class AlphaAgentQlibFactorHypothesisExperiment2Feedback(HypothesisExperiment2Feedback):
    def generate_feedback(self, exp: Experiment, hypothesis: Hypothesis, trace: Trace) -> HypothesisFeedback:
        """
        Generate feedback for the given experiment and hypothesis.

        Args:
            exp (QlibFactorExperiment): The experiment to generate feedback for.
            hypothesis (QlibFactorHypothesis): The hypothesis to generate feedback for.
            trace (Trace): The trace of the experiment.

        Returns:
            Any: The feedback generated for the given experiment and hypothesis.
        """
        logger.info("Generating feedback...")
        hypothesis_text = hypothesis.hypothesis
        current_result = exp.result
        tasks_factors = [task.get_task_information_and_implementation_result() for task in exp.sub_tasks]
        # Safely get SOTA result, handle case where based_experiments might be empty or result is None
        sota_result = None
        if exp.based_experiments and len(exp.based_experiments) > 0:
            sota_result = exp.based_experiments[-1].result

        # Extract complexity information by directly calculating from factor expressions
        # Import complexity calculation functions
        try:
            from quantaalpha.factors.coder.factor_ast import (
                calculate_symbol_length, count_base_features
            )
            from quantaalpha.factors.coder.config import FACTOR_COSTEER_SETTINGS
            
            for idx, task_detail in enumerate(tasks_factors):
                if idx < len(exp.sub_tasks):
                    task = exp.sub_tasks[idx]
                    factor_expr = task_detail.get("factor_expression", "")
                    if factor_expr:
                        complexity_warnings = []
                        # Calculate symbol length
                        symbol_length = calculate_symbol_length(factor_expr)
                        symbol_length_threshold = getattr(FACTOR_COSTEER_SETTINGS, 'symbol_length_threshold', 300)
                        if symbol_length > symbol_length_threshold:
                            complexity_warnings.append(
                                f"Symbol Length (SL) Check Failed: Symbol length ({symbol_length}) exceeds threshold ({symbol_length_threshold}). "
                                f"The factor expression is too complex and may lead to overfitting."
                            )
                        
                        # Calculate base features count
                        num_base_features = count_base_features(factor_expr)
                        base_features_threshold = getattr(FACTOR_COSTEER_SETTINGS, 'base_features_threshold', 6)
                        if num_base_features > base_features_threshold:
                            complexity_warnings.append(
                                f"Base Features Count (ER) Check Failed: Number of base features ({num_base_features}) exceeds threshold ({base_features_threshold}). "
                                f"The factor uses too many raw features, which may indicate over-engineering."
                            )
                        
                        if complexity_warnings:
                            task_detail["complexity_feedback"] = "\n".join(complexity_warnings)
        except Exception as e:
            logger.warning(f"Failed to calculate complexity info: {e}")

        # Process the results to filter important metrics
        combined_result = process_results(current_result, sota_result)

        # Compute per-regime performance table if regime map is available
        regime_map = getattr(self, 'regime_map', None)
        regime_table = None
        if regime_map is not None:
            regime_table = build_regime_table(exp, regime_map)

        # Generate the system prompt
        sys_prompt = (
            Environment(undefined=StrictUndefined)
            .from_string(qa_feedback_prompts["factor_feedback_generation"]["system"])
            .render(scenario=self.scen.get_scenario_all_desc())
        )

        # Generate the user prompt
        usr_prompt = (
            Environment(undefined=StrictUndefined)
            .from_string(qa_feedback_prompts["factor_feedback_generation"]["user"])
            .render(
                hypothesis_text=hypothesis_text,
                task_details=tasks_factors,
                combined_result=combined_result,
                regime_table=regime_table,
            )
        )

        # Debug: save full prompt to file when regime analysis is present
        if regime_table is not None:
            try:
                prompt_dump_path = logger.log_trace_path / "regime_feedback_prompt.txt"
                prompt_dump_path.write_text(usr_prompt, encoding="utf-8")
                logger.info(f"Regime feedback prompt saved to {prompt_dump_path}")
            except Exception:
                pass

        # Call the APIBackend to generate the response for hypothesis feedback with retry
        response_json = None
        last_error = None

        for attempt in range(MAX_JSON_PARSE_RETRIES):
            try:
                response = APIBackend().build_messages_and_create_chat_completion(
                    user_prompt=usr_prompt,
                    system_prompt=sys_prompt,
                    json_mode=True,
                )
                # Parse the JSON response using robust parser
                response_json = robust_json_parse(response)
                break
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(f"[AlphaAgent] JSON parse failed (attempt {attempt + 1}/{MAX_JSON_PARSE_RETRIES}): {e}")
                if attempt < MAX_JSON_PARSE_RETRIES - 1:
                    logger.info("[AlphaAgent] Re-requesting LLM...")
                continue

        if response_json is None:
            logger.error(f"[AlphaAgent] JSON parse still failed after {MAX_JSON_PARSE_RETRIES} attempts")
            return HypothesisFeedback(
                observations="JSON parse failed; could not extract feedback",
                hypothesis_evaluation="Unable to evaluate",
                new_hypothesis="",
                reason=f"JSON parse error: {last_error}",
                decision=False,
            )

        # Extract fields from JSON response
        observations = response_json.get("Observations", "No observations provided")
        hypothesis_evaluation = response_json.get("Feedback for Hypothesis", "No feedback provided")
        new_hypothesis = response_json.get("New Hypothesis", "No new hypothesis provided")
        reason = response_json.get("Reasoning", "No reasoning provided")
        decision = convert2bool(response_json.get("Replace Best Result", "no"))

        return HypothesisFeedback(
            observations=observations,
            hypothesis_evaluation=hypothesis_evaluation,
            new_hypothesis=new_hypothesis,
            reason=reason,
            decision=decision,
        )


class QlibModelHypothesisExperiment2Feedback(HypothesisExperiment2Feedback):
    """Generated feedbacks on the hypothesis from **Executed** Implementations of different tasks & their comparisons with previous performances"""

    def generate_feedback(self, exp: Experiment, hypothesis: Hypothesis, trace: Trace) -> HypothesisFeedback:
        """
        The `ti` should be executed and the results should be included, as well as the comparison between previous results (done by LLM).
        For example: `mlflow` of Qlib will be included.
        """

        logger.info("Generating feedback...")
        # Define the system prompt for hypothesis feedback
        system_prompt = feedback_prompts["model_feedback_generation"]["system"]

        # Define the user prompt for hypothesis feedback
        context = trace.scen
        SOTA_hypothesis, SOTA_experiment = trace.get_sota_hypothesis_and_experiment()

        user_prompt = (
            Environment(undefined=StrictUndefined)
            .from_string(feedback_prompts["model_feedback_generation"]["user"])
            .render(
                context=context,
                last_hypothesis=SOTA_hypothesis,
                last_task=SOTA_experiment.sub_tasks[0].get_task_information() if SOTA_hypothesis else None,
                last_code=SOTA_experiment.sub_workspace_list[0].code_dict.get("model.py") if SOTA_hypothesis else None,
                last_result=SOTA_experiment.result if SOTA_hypothesis else None,
                hypothesis=hypothesis,
                exp=exp,
            )
        )

        # Call the APIBackend to generate the response for hypothesis feedback with retry
        response_json_hypothesis = None
        last_error = None
        
        for attempt in range(MAX_JSON_PARSE_RETRIES):
            try:
                response_hypothesis = APIBackend().build_messages_and_create_chat_completion(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    json_mode=True,
                )
                # Parse the JSON response using robust parser
                response_json_hypothesis = robust_json_parse(response_hypothesis)
                break
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning(f"[Model] JSON parse failed (attempt {attempt + 1}/{MAX_JSON_PARSE_RETRIES}): {e}")
                if attempt < MAX_JSON_PARSE_RETRIES - 1:
                    logger.info("[Model] Re-requesting LLM...")
                continue
        
        if response_json_hypothesis is None:
            logger.error(f"[Model] JSON parse still failed after {MAX_JSON_PARSE_RETRIES} attempts")
            return HypothesisFeedback(
                observations="JSON parse failed; could not extract feedback",
                hypothesis_evaluation="Unable to evaluate",
                new_hypothesis="",
                reason=f"JSON parse error: {last_error}",
                decision=False,
            )
        
        return HypothesisFeedback(
            observations=response_json_hypothesis.get("Observations", "No observations provided"),
            hypothesis_evaluation=response_json_hypothesis.get("Feedback for Hypothesis", "No feedback provided"),
            new_hypothesis=response_json_hypothesis.get("New Hypothesis", "No new hypothesis provided"),
            reason=response_json_hypothesis.get("Reasoning", "No reasoning provided"),
            decision=convert2bool(response_json_hypothesis.get("Decision", "false")),
        )
