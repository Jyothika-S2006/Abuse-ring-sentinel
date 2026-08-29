"""
agent/agent.py -- orchestration entry point.
Replaces the old deterministic explain_cluster() call used by the FastAPI route.
"""

from .investigator import investigate_cluster
from .critic import critique_investigation


def run_full_investigation(cluster_id: str) -> dict:
    """
    Runs investigator -> critic in sequence and returns the combined structured result
    the API route and frontend should use.
    """
    investigator_report = investigate_cluster(cluster_id)
    critique = critique_investigation(cluster_id, investigator_report)

    return {
        "cluster_id": cluster_id,
        "investigation": investigator_report,
        "critique": critique,
        "final_confidence": critique.get("adjusted_confidence", investigator_report.get("confidence")),
        "final_recommendation": critique.get("final_recommendation", "needs_human_review"),
    }