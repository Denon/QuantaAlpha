#!/usr/bin/env python3
"""
Seed the Knowledge Graph with existing factors from the factor library.

This script reads all factors from data/factorlib/all_factors_library.json,
creates knowledge graph nodes and CoSTEERKnowledge objects for each factor,
and persists both the graph (graph.pkl) and the companion knowledge dicts
(graph_knowledge_dicts.pkl) to disk.

Usage:
    cd /home/darren/myproject/QuantaAlpha
    conda run -n rdagent python scripts/seed_knowledge_graph.py
"""

import json
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing quantaalpha modules (which initialize LLM_SETTINGS)
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv(".env")

import dill as pickle

from quantaalpha.coder.costeer.knowledge_management import (
    CoSTEERKnowledge,
    CoSTEERKnowledgeBaseV2,
)
from quantaalpha.coder.costeer.evaluators import CoSTEERSingleFeedback
from quantaalpha.coder.knowledge.graph import UndirectedNode
from quantaalpha.factors.coder.factor import FactorFBWorkspace, FactorTask
from quantaalpha.log import logger


def load_factor_library(path: str = "data/factorlib/all_factors_library.json") -> dict:
    """Load the factor library JSON file."""
    with open(path) as f:
        return json.load(f)


def build_task_info(factor: dict) -> str:
    """Build a task information string matching FactorTask.get_task_information() format."""
    return (
        f"factor_name: {factor['factor_name']}\n"
        f"factor_description: {factor['factor_description']}\n"
        f"factor_formulation: {factor['factor_formulation']}\n"
        f"variables: {{}}"
    )


def build_implementation_feedback_str(implementation_code: str, feedback: str) -> str:
    """Build the implementation + feedback string matching CoSTEERKnowledge format."""
    return (
        f"------------------implementation code:------------------\n"
        f"{implementation_code}\n"
        f"------------------implementation feedback:------------------\n"
        f"{feedback}"
    )


def seed_knowledge_graph(factor_library_path: str = "data/factorlib/all_factors_library.json") -> None:
    """Main entry point: load factors, seed knowledge graph, persist to disk."""
    library = load_factor_library(factor_library_path)
    factors = library["factors"]
    logger.info(f"Loaded {len(factors)} factors from {factor_library_path}")

    # Create fresh knowledge base
    kb = CoSTEERKnowledgeBaseV2()
    graph = kb.graph

    seeded_count = 0
    for factor_id, factor in factors.items():
        # Skip factors without implementation code
        impl_code = factor.get("factor_implementation_code")
        if not impl_code:
            logger.warning(f"Skipping {factor_id}: no implementation code")
            continue

        # Build task info string (used as task_description node content)
        task_info = build_task_info(factor)

        # Skip if this task info already exists in success dict
        if task_info in kb.success_task_to_knowledge_dict:
            logger.debug(f"Skipping duplicate task: {factor['factor_name']}")
            continue

        # Build implementation + feedback node content
        # Use stored feedback observations if available, otherwise a placeholder
        fb_data = factor.get("feedback", {})
        fb_str = fb_data.get("observations", "Historical factor (seeded from factor library)")

        impl_fb_str = build_implementation_feedback_str(impl_code, fb_str)

        # Determine whether this factor passed (final_decision = True in feedback)
        # Default to True for factors that exist in the library (they were kept)
        fb_decision = fb_data.get("decision", True)

        # Create CoSTEERKnowledge components
        task = FactorTask(
            factor_name=factor["factor_name"],
            factor_description=factor.get("factor_description", ""),
            factor_formulation=factor.get("factor_formulation", ""),
            factor_expression=factor.get("factor_expression", ""),
            variables={},
        )

        workspace = FactorFBWorkspace(target_task=task)
        workspace.code_dict["factor.py"] = impl_code

        feedback = CoSTEERSingleFeedback(
            execution_feedback="(seeded from historical factor)",
            final_decision=fb_decision,
            value_generated_flag=True,
            final_decision_based_on_gt=False,
            final_feedback=fb_str,
        )

        knowledge = CoSTEERKnowledge(
            target_task=task,
            implementation=workspace,
            feedback=feedback,
        )

        # Create graph nodes (embedding will be computed via configured API)
        task_des_node = UndirectedNode(content=task_info, label="task_description")
        success_node = UndirectedNode(content=impl_fb_str, label="task_success_implement")

        # Add to graph: task_description <-> task_success_implement
        graph.add_nodes(node=task_des_node, neighbors=[])
        graph.add_nodes(node=success_node, neighbors=[task_des_node])

        # Populate knowledge dicts
        kb.node_to_implementation_knowledge_dict[success_node.id] = knowledge
        kb.success_task_to_knowledge_dict[task_info] = knowledge

        seeded_count += 1
        logger.info(f"Seeded: {factor['factor_name']} (decision={fb_decision})")

    logger.info(f"Seeded {seeded_count} factors into knowledge graph")

    # Persist graph
    graph.dump()
    logger.info(f"Graph saved to graph.pkl, size={graph.size()}")

    # Persist companion knowledge dicts
    dicts_path = Path.cwd() / "graph_knowledge_dicts.pkl"
    pickle.dump(
        {
            "node_to_implementation_knowledge_dict": kb.node_to_implementation_knowledge_dict,
            "success_task_to_knowledge_dict": kb.success_task_to_knowledge_dict,
        },
        open(dicts_path, "wb"),
    )
    logger.info(f"Knowledge dicts saved to {dicts_path}")


if __name__ == "__main__":
    seed_knowledge_graph()
