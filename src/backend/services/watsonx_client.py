"""
watsonx_client — Phase 4: IBM watsonx.ai Granite integration.

Reads configuration from environment variables:
  WATSONX_API_KEY      — IBM Cloud API key
  WATSONX_PROJECT_ID   — watsonx.ai project ID
  WATSONX_URL          — regional endpoint (default: https://us-south.ml.cloud.ibm.com)
  WATSONX_MODEL_ID     — Granite model ID (default: ibm/granite-3-8b-instruct)

If credentials are missing or the API call fails, generate_summary() returns a
template-filled fallback string with ai_generated=False so the application always
has a usable response.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK imports — module-level so tests can patch them cleanly.
# Guarded so the app still starts if the package is not installed.
# ---------------------------------------------------------------------------
try:
    from ibm_watsonx_ai import Credentials  # noqa: F401
    from ibm_watsonx_ai.foundation_models import ModelInference  # noqa: F401
    _SDK_AVAILABLE = True
except ImportError:
    Credentials = None  # type: ignore[assignment,misc]
    ModelInference = None  # type: ignore[assignment,misc]
    _SDK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(stats: dict) -> str:
    """Construct the structured prompt sent to watsonx Granite."""
    active = stats.get("active_disruptions", 0)
    at_risk = stats.get("shipments_at_risk", 0)
    idle = stats.get("idle_fleet", 0)
    excursions = stats.get("cold_chain_excursions", 0)
    critical = stats.get("critical_excursions", 0)

    # Breakdown strings from optional enriched stats
    breakdown = stats.get("disruption_breakdown", "")
    top_shipment = stats.get("top_shipment", "")
    top_reco = stats.get("top_recommendation", "Check rerouting options for at-risk shipments")

    breakdown_str = f" ({breakdown})" if breakdown else ""
    top_shp_str = f" (top risk: {top_shipment})" if top_shipment else ""

    return (
        "You are FLEETIQ, an expert supply chain operations assistant.\n"
        "Summarise the current operational status and provide prioritised action items.\n"
        "\n"
        "Current Data:\n"
        f"- Active disruptions: {active}{breakdown_str}\n"
        f"- Shipments at risk: {at_risk}{top_shp_str}\n"
        f"- Idle fleet available: {idle} vehicles\n"
        f"- Cold-chain excursions: {excursions} active, {critical} critical\n"
        f"- Top recommendation: {top_reco}\n"
        "\n"
        "Provide:\n"
        "1. One-paragraph operational summary (3-4 sentences, executive tone)\n"
        "2. Top 3 prioritised action items (numbered list)\n"
        "3. One risk the team should watch in the next 24 hours\n"
    )


def _fallback_summary(stats: dict) -> str:
    """Return a deterministic template string populated with real DB stats."""
    active = stats.get("active_disruptions", 0)
    at_risk = stats.get("shipments_at_risk", 0)
    idle = stats.get("idle_fleet", 0)
    excursions = stats.get("cold_chain_excursions", 0)
    critical = stats.get("critical_excursions", 0)

    return (
        f"FLEETIQ Operational Status Summary\n\n"
        f"Current status: {active} active disruption(s) requiring attention, "
        f"{at_risk} shipment(s) at risk, "
        f"{idle} idle fleet vehicle(s) available for redeployment, "
        f"and {excursions} cold-chain excursion(s) ({critical} critical).\n\n"
        f"Recommended actions:\n"
        f"1. Review and action the {at_risk} at-risk shipment(s) — assess rerouting options.\n"
        f"2. Redeploy {idle} idle vehicle(s) to cover disrupted routes.\n"
        f"3. Escalate the {critical} critical cold-chain excursion(s) to quality control.\n\n"
        f"Risk to watch: Monitor active disruptions for escalation in the next 24 hours.\n\n"
        f"[Note: AI generation requires WATSONX_API_KEY, WATSONX_PROJECT_ID, "
        f"and WATSONX_URL environment variables.]"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_summary(stats: dict) -> dict:
    """
    Generate an AI operational summary using IBM watsonx.ai Granite.

    Parameters
    ----------
    stats : dict
        Operational statistics dict from /api/summary/stats, optionally
        enriched with 'disruption_breakdown', 'top_shipment',
        'top_recommendation' keys.

    Returns
    -------
    dict with keys:
      summary (str)    — generated or fallback text
      ai_generated (bool) — True if watsonx call succeeded
      model_id (str)   — model that was used (or None for fallback)
    """
    api_key = os.getenv("WATSONX_API_KEY", "").strip()
    project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").strip()
    model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct").strip()

    # --- credentials check ---
    if not api_key or not project_id:
        logger.info(
            "watsonx credentials not configured — returning fallback summary. "
            "Set WATSONX_API_KEY and WATSONX_PROJECT_ID to enable AI generation."
        )
        return {
            "summary": _fallback_summary(stats),
            "ai_generated": False,
            "model_id": None,
        }

    # --- SDK call ---
    try:
        credentials = Credentials(url=url, api_key=api_key)
        model = ModelInference(
            model_id=model_id,
            credentials=credentials,
            project_id=project_id,
        )
        prompt = _build_prompt(stats)
        result = model.generate_text(
            prompt=prompt,
            params={"max_new_tokens": 400, "temperature": 0.3},
        )
        generated_text = result.strip() if isinstance(result, str) else str(result).strip()
        return {
            "summary": generated_text,
            "ai_generated": True,
            "model_id": model_id,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("watsonx API call failed (%s) — returning fallback summary.", exc)
        return {
            "summary": _fallback_summary(stats),
            "ai_generated": False,
            "model_id": None,
        }
