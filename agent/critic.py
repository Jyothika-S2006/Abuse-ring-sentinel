"""
agent/critic.py
Second-pass skeptic agent, using the current google-genai SDK.
Takes the investigator's report and actively looks for innocent explanations
before a cluster becomes a final flag.
"""

import json
from google.genai import types

from .investigator import client, MODEL_NAME, TOOLS, _parse_json_response, _generate_with_retry

CRITIC_SYSTEM_PROMPT = """You are a skeptical second-reviewer for Razorpay's Abuse-Ring Sentinel.

You are given a cluster_id and another agent's investigation report claiming it looks like
coordinated abuse. Your job is to actively try to find INNOCENT explanations for the same evidence
before this becomes a final flag -- for example: a shared IP could be a family or small office
network; a shared device could be a shared family phone; elevated velocity could be a legitimate
seasonal spike. Use the tools to check account context (KYC status, account age, behavior diversity)
that would support or undermine an innocent explanation.

Do not simply agree with the investigator. Genuinely look for reasons this could be a false positive.

Return your final answer as a single JSON object with exactly these fields:
{
  "counter_considerations": ["<specific innocent explanations you checked, and what you found>"],
  "adjusted_confidence": <float 0-1, your own confidence this is genuine abuse after skepticism>,
  "final_recommendation": "<one of: confirm_likely_fraud, needs_human_review, likely_false_positive>"
}
Output ONLY the JSON object, no other text.
"""


def critique_investigation(cluster_id: str, investigator_report: dict) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=CRITIC_SYSTEM_PROMPT,
        tools=TOOLS,
    )
    prompt = (
        f"cluster_id: {cluster_id}\n\n"
        f"Investigator's report to critique:\n{json.dumps(investigator_report, indent=2)}"
    )
    response = _generate_with_retry(
        model=MODEL_NAME,
        contents=prompt,
        config=config,
    )

    parsed = _parse_json_response(response.text)
    if parsed is not None:
        return parsed

    return {
        "counter_considerations": [],
        "adjusted_confidence": investigator_report.get("confidence", 0.0),
        "final_recommendation": "needs_human_review",
        "parse_error": True,
    }