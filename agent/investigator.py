"""
agent/investigator.py
Gemini-powered investigation agent, using the current google-genai SDK.
Includes retry-with-backoff since the free tier for gemini-3.6-flash
is a tight 5 requests/minute.
"""

import os
import json
import time
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv

from .tools import (
    get_cluster_features,
    get_shared_signal_evidence,
    get_account_details,
    get_similar_historical_cases,
)

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL_NAME = "gemini-3.6-flash"

INVESTIGATOR_SYSTEM_PROMPT = """You are a fraud-risk investigation agent for Razorpay's Abuse-Ring Sentinel.

You are given a cluster_id that a graph + ML pipeline already flagged as a candidate coordinated
abuse ring. Investigate it using ONLY the tools provided. Do not invent facts -- every claim in your
final report must be traceable to a tool result.

Process:
1. Call get_cluster_features to see the model's risk score and the 9 structural/behavioral features.
2. Call get_shared_signal_evidence to see exactly which accounts share which signals.
3. Call get_account_details on at least the two or three most central accounts (KYC status, behavior).
4. Call get_similar_historical_cases to see if analysts have confirmed or dismissed similar clusters before.
5. Once you have enough evidence, stop calling tools and produce your final report.

Return your final answer as a single JSON object with exactly these fields:
{
  "summary": "<2-3 sentence plain-English summary of why this looks like coordinated abuse>",
  "shared_signals": ["<specific shared signals found, e.g. '4 accounts share device_id X'>"],
  "behavioral_flags": ["<specific behavioral evidence, e.g. 'decline_rate 0.62, consistent with card testing'>"],
  "confidence": <float 0-1>,
  "recommended_action": "<one of: review, escalate>"
}
Output ONLY the JSON object, no other text.
"""

TOOLS = [
    get_cluster_features,
    get_shared_signal_evidence,
    get_account_details,
    get_similar_historical_cases,
]


def _parse_json_response(raw_text: str) -> dict:
    raw_text = (raw_text or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text.split("\n", 1)[-1]
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return None


def _generate_with_retry(model: str, contents: str, config, max_retries: int = 5, default_wait: int = 15):
    """Calls generate_content, retrying on 429 rate-limit errors with backoff.
    Free tier is tight (5 req/min for gemini-3.6-flash) -- this makes dev/demo
    usage reliable instead of crashing on the first burst of calls."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.ClientError as e:
            is_rate_limit = getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
            if not is_rate_limit:
                raise
            last_error = e
            wait_seconds = default_wait * (attempt + 1)
            print(f"[rate limited] attempt {attempt + 1}/{max_retries}, waiting {wait_seconds}s...")
            time.sleep(wait_seconds)
    raise last_error


def investigate_cluster(cluster_id: str) -> dict:
    """Runs the tool-calling investigation for one cluster. The SDK automatically
    calls the Python functions in TOOLS based on their type hints/docstrings."""
    config = types.GenerateContentConfig(
        system_instruction=INVESTIGATOR_SYSTEM_PROMPT,
        tools=TOOLS,
    )
    response = _generate_with_retry(
        model=MODEL_NAME,
        contents=f"Investigate cluster_id: {cluster_id}",
        config=config,
    )

    parsed = _parse_json_response(response.text)
    if parsed is not None:
        return parsed

    return {
        "summary": (response.text or "").strip(),
        "shared_signals": [],
        "behavioral_flags": [],
        "confidence": 0.0,
        "recommended_action": "review",
        "parse_error": True,
    }