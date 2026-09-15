"""
FLEETIQ Phase 4 — watsonx.ai Integration Tests
===============================================

Test groups:
  A. Unit tests — watsonx_client (no DB, no real API calls)
       1. Fallback without credentials (env vars absent)
       2. Fallback when only API key is set (project_id missing)
       3. Fallback when only project_id is set (api_key missing)
       4. Environment configuration — model_id read from env, not hardcoded
       5. Environment configuration — URL read from env
       6. Successful mocked watsonx generation (ai_generated=True)
       7. API failure fallback (exception during SDK call)
       8. Fallback summary contains real stats values
       9. Prompt contains all required sections
      10. Prompt reflects stats dict values
      11. generate_summary return dict has required keys
      12. Mocked result returns model_id in response

  B. Integration tests — /api/summary and /api/summary/stats
      13. GET /api/summary/stats returns 200 with expected keys
      14. GET /api/summary/stats returns correct DB-seeded values
      15. GET /api/summary returns 200 with expected keys
      16. GET /api/summary has 'summary', 'stats', 'ai_generated', 'model_id'
      17. Without credentials, ai_generated=False
      18. Without credentials, summary contains real stat numbers
      19. model_id is None when fallback is used
      20. stats sub-dict in /api/summary response matches /api/summary/stats

  C. Phase 2 + Phase 3 regression — ensure nothing broke
      21. /health still OK
      22. /api/disruptions still returns 5 items
      23. /api/shipments still returns 15 items
      24. /api/fleet still returns 10 items
      25. /api/cold-chain still returns 11 items
"""

import sys
import os
import unittest.mock as mock
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Put backend on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.watsonx_client import (
    generate_summary,
    _build_prompt,
    _fallback_summary,
)
from main import app


# ===========================================================================
# A — Unit tests: watsonx_client
# ===========================================================================

class TestWatsonxClientUnit:
    """
    All tests in this class use monkeypatch to clear env vars and mock
    the SDK. No real API calls are ever made.
    """

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    SAMPLE_STATS = {
        "active_disruptions": 3,
        "shipments_at_risk": 5,
        "idle_fleet": 4,
        "cold_chain_excursions": 6,
        "critical_excursions": 2,
        "disruption_breakdown": "2 port_congestion, 1 severe_weather",
        "top_shipment": "FQ-2026-00001 (impact score 87.5)",
        "top_recommendation": "Reroute critical shipments via alternate carriers",
    }

    def _clear_credentials(self, monkeypatch):
        """Remove all watsonx env vars."""
        for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "WATSONX_MODEL_ID"):
            monkeypatch.delenv(var, raising=False)

    def _set_credentials(self, monkeypatch, api_key="test-key", project_id="test-project"):
        """Set minimal valid credentials."""
        monkeypatch.setenv("WATSONX_API_KEY", api_key)
        monkeypatch.setenv("WATSONX_PROJECT_ID", project_id)
        monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

    # -----------------------------------------------------------------------
    # 1. Fallback without any credentials
    # -----------------------------------------------------------------------

    def test_fallback_when_no_credentials(self, monkeypatch):
        """With no credentials at all, ai_generated must be False."""
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert result["ai_generated"] is False
        assert result["model_id"] is None
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    # -----------------------------------------------------------------------
    # 2. Fallback when only api_key is set
    # -----------------------------------------------------------------------

    def test_fallback_when_project_id_missing(self, monkeypatch):
        """With only WATSONX_API_KEY set (no project_id), must fall back."""
        self._clear_credentials(monkeypatch)
        monkeypatch.setenv("WATSONX_API_KEY", "some-api-key")
        result = generate_summary(self.SAMPLE_STATS)
        assert result["ai_generated"] is False

    # -----------------------------------------------------------------------
    # 3. Fallback when only project_id is set
    # -----------------------------------------------------------------------

    def test_fallback_when_api_key_missing(self, monkeypatch):
        """With only WATSONX_PROJECT_ID set (no api_key), must fall back."""
        self._clear_credentials(monkeypatch)
        monkeypatch.setenv("WATSONX_PROJECT_ID", "some-project-id")
        result = generate_summary(self.SAMPLE_STATS)
        assert result["ai_generated"] is False

    # -----------------------------------------------------------------------
    # 4. Environment configuration — model_id from env
    # -----------------------------------------------------------------------

    def test_model_id_read_from_env(self, monkeypatch):
        """
        WATSONX_MODEL_ID must be read from environment — never hardcoded.
        When credentials are valid, the model_id in the result must match
        the env var, not a hardcoded constant.
        """
        self._set_credentials(monkeypatch)
        monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-3-2b-instruct")

        with (
            patch("services.watsonx_client.Credentials") as mock_creds,
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = "AI generated text"
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["ai_generated"] is True
        assert result["model_id"] == "ibm/granite-3-2b-instruct"

    def test_default_model_id_is_granite_3_8b(self, monkeypatch):
        """Default model ID (when env var absent) must be ibm/granite-3-8b-instruct."""
        self._set_credentials(monkeypatch)
        monkeypatch.delenv("WATSONX_MODEL_ID", raising=False)

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = "text"
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["model_id"] == "ibm/granite-3-8b-instruct"

    # -----------------------------------------------------------------------
    # 5. Environment configuration — URL from env
    # -----------------------------------------------------------------------

    def test_url_passed_to_credentials(self, monkeypatch):
        """WATSONX_URL must be passed to the Credentials constructor."""
        self._set_credentials(monkeypatch)
        monkeypatch.setenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com")

        with (
            patch("services.watsonx_client.Credentials") as mock_creds,
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = "text"
            mock_mi.return_value = mock_instance

            generate_summary(self.SAMPLE_STATS)

        # Credentials must be called with the URL we set
        call_kwargs = mock_creds.call_args
        assert call_kwargs is not None
        # Accept both positional and keyword
        all_args = list(call_kwargs.args) + list(call_kwargs.kwargs.values())
        assert any("eu-de.ml.cloud.ibm.com" in str(a) for a in all_args)

    # -----------------------------------------------------------------------
    # 6. Successful mocked watsonx generation
    # -----------------------------------------------------------------------

    def test_successful_generation_ai_generated_true(self, monkeypatch):
        """When SDK call succeeds, ai_generated must be True."""
        self._set_credentials(monkeypatch)

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = (
                "Operational summary: 3 disruptions active. "
                "Action 1: Reroute. Action 2: Deploy fleet. Action 3: Escalate cold chain."
            )
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["ai_generated"] is True
        assert "Operational summary" in result["summary"]
        assert isinstance(result["summary"], str)

    def test_successful_generation_returns_model_text(self, monkeypatch):
        """The summary field must contain exactly what generate_text returns."""
        self._set_credentials(monkeypatch)
        expected_text = "Unique sentinel text 🔍 ABC-123"

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = expected_text
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["summary"] == expected_text.strip()

    def test_generate_text_called_with_params(self, monkeypatch):
        """generate_text must be called with max_new_tokens and temperature."""
        self._set_credentials(monkeypatch)

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = "text"
            mock_mi.return_value = mock_instance

            generate_summary(self.SAMPLE_STATS)

        call_kwargs = mock_instance.generate_text.call_args
        assert call_kwargs is not None
        params = call_kwargs.kwargs.get("params") or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        assert params is not None
        assert params.get("max_new_tokens") == 400
        assert params.get("temperature") == 0.3

    # -----------------------------------------------------------------------
    # 7. API failure fallback
    # -----------------------------------------------------------------------

    def test_api_failure_returns_fallback(self, monkeypatch):
        """If the SDK raises an exception, ai_generated must be False."""
        self._set_credentials(monkeypatch)

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.side_effect = RuntimeError("API timeout")
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["ai_generated"] is False
        assert result["model_id"] is None
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

    def test_credentials_init_failure_returns_fallback(self, monkeypatch):
        """If Credentials() itself raises, must fall back gracefully."""
        self._set_credentials(monkeypatch)

        with patch("services.watsonx_client.Credentials") as mock_creds:
            mock_creds.side_effect = Exception("Invalid credentials")
            result = generate_summary(self.SAMPLE_STATS)

        assert result["ai_generated"] is False

    # -----------------------------------------------------------------------
    # 8. Fallback summary contains real stats values
    # -----------------------------------------------------------------------

    def test_fallback_summary_contains_active_disruption_count(self, monkeypatch):
        """Fallback text must include the real active disruption count."""
        self._clear_credentials(monkeypatch)
        stats = dict(self.SAMPLE_STATS)
        stats["active_disruptions"] = 7
        result = generate_summary(stats)
        assert "7" in result["summary"]

    def test_fallback_summary_contains_at_risk_count(self, monkeypatch):
        """Fallback text must include the shipments_at_risk count."""
        self._clear_credentials(monkeypatch)
        stats = dict(self.SAMPLE_STATS)
        stats["shipments_at_risk"] = 13
        result = generate_summary(stats)
        assert "13" in result["summary"]

    def test_fallback_summary_contains_idle_fleet_count(self, monkeypatch):
        """Fallback text must include the idle_fleet count."""
        self._clear_credentials(monkeypatch)
        stats = dict(self.SAMPLE_STATS)
        stats["idle_fleet"] = 9
        result = generate_summary(stats)
        assert "9" in result["summary"]

    def test_fallback_summary_contains_critical_count(self, monkeypatch):
        """Fallback text must include critical_excursions count."""
        self._clear_credentials(monkeypatch)
        stats = dict(self.SAMPLE_STATS)
        stats["critical_excursions"] = 5
        result = generate_summary(stats)
        assert "5" in result["summary"]

    def test_fallback_summary_has_credential_note(self, monkeypatch):
        """Fallback must mention that credentials are required for AI generation."""
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert "WATSONX_API_KEY" in result["summary"] or "credentials" in result["summary"].lower()

    # -----------------------------------------------------------------------
    # 9. Prompt contains all required sections
    # -----------------------------------------------------------------------

    def test_prompt_contains_system_persona(self):
        """Prompt must establish FLEETIQ as an expert supply chain assistant."""
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "FLEETIQ" in prompt
        assert "supply chain" in prompt.lower()

    def test_prompt_contains_disruption_section(self):
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "Active disruptions" in prompt or "disruptions" in prompt.lower()

    def test_prompt_contains_shipments_section(self):
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "Shipments at risk" in prompt or "at risk" in prompt.lower()

    def test_prompt_contains_fleet_section(self):
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "fleet" in prompt.lower() or "vehicles" in prompt.lower()

    def test_prompt_contains_cold_chain_section(self):
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "cold-chain" in prompt.lower() or "excursion" in prompt.lower()

    def test_prompt_requests_action_items(self):
        """Prompt must explicitly request prioritised action items."""
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "action" in prompt.lower() or "prioritis" in prompt.lower()

    def test_prompt_requests_risk_watch(self):
        """Prompt must ask for a risk to watch."""
        prompt = _build_prompt(self.SAMPLE_STATS)
        assert "risk" in prompt.lower() or "watch" in prompt.lower()

    # -----------------------------------------------------------------------
    # 10. Prompt reflects stats dict values
    # -----------------------------------------------------------------------

    def test_prompt_includes_disruption_count(self):
        prompt = _build_prompt({"active_disruptions": 7, "shipments_at_risk": 0,
                                 "idle_fleet": 0, "cold_chain_excursions": 0, "critical_excursions": 0})
        assert "7" in prompt

    def test_prompt_includes_idle_fleet_count(self):
        prompt = _build_prompt({"active_disruptions": 0, "shipments_at_risk": 0,
                                 "idle_fleet": 11, "cold_chain_excursions": 0, "critical_excursions": 0})
        assert "11" in prompt

    def test_prompt_includes_breakdown(self):
        """Optional breakdown string must appear in the prompt when provided."""
        prompt = _build_prompt({**self.SAMPLE_STATS, "disruption_breakdown": "2 port_congestion"})
        assert "port_congestion" in prompt

    def test_prompt_includes_top_shipment(self):
        """Optional top_shipment string must appear in the prompt when provided."""
        prompt = _build_prompt({**self.SAMPLE_STATS, "top_shipment": "FQ-SENTINEL-999"})
        assert "FQ-SENTINEL-999" in prompt

    # -----------------------------------------------------------------------
    # 11. Return dict structure
    # -----------------------------------------------------------------------

    def test_return_dict_has_summary_key(self, monkeypatch):
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert "summary" in result

    def test_return_dict_has_ai_generated_key(self, monkeypatch):
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert "ai_generated" in result

    def test_return_dict_has_model_id_key(self, monkeypatch):
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert "model_id" in result

    # -----------------------------------------------------------------------
    # 12. Mocked result returns model_id in response
    # -----------------------------------------------------------------------

    def test_model_id_in_result_on_success(self, monkeypatch):
        """On success, model_id in result must equal WATSONX_MODEL_ID env var."""
        self._set_credentials(monkeypatch)
        monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-13b-chat-v2")

        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = "Generated."
            mock_mi.return_value = mock_instance

            result = generate_summary(self.SAMPLE_STATS)

        assert result["model_id"] == "ibm/granite-13b-chat-v2"

    def test_model_id_is_none_on_fallback(self, monkeypatch):
        """On fallback (no credentials), model_id must be None."""
        self._clear_credentials(monkeypatch)
        result = generate_summary(self.SAMPLE_STATS)
        assert result["model_id"] is None


# ===========================================================================
# B — Integration tests: /api/summary and /api/summary/stats
# ===========================================================================

@pytest_asyncio.fixture(scope="module")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.anyio
async def test_summary_stats_returns_200(client):
    r = await client.get("/api/summary/stats")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_summary_stats_has_required_keys(client):
    r = await client.get("/api/summary/stats")
    data = r.json()
    for key in ("active_disruptions", "shipments_at_risk", "idle_fleet",
                "cold_chain_excursions", "critical_excursions"):
        assert key in data, f"Missing key: {key}"


@pytest.mark.anyio
async def test_summary_stats_correct_seeded_values(client):
    """Verify stats match the deterministic seed data."""
    r = await client.get("/api/summary/stats")
    data = r.json()
    assert data["active_disruptions"] == 3
    assert data["idle_fleet"] == 4
    assert data["cold_chain_excursions"] == 6


@pytest.mark.anyio
async def test_summary_returns_200(client):
    r = await client.get("/api/summary")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_summary_has_all_required_keys(client):
    r = await client.get("/api/summary")
    data = r.json()
    for key in ("summary", "stats", "ai_generated", "model_id"):
        assert key in data, f"Missing key: {key}"


@pytest.mark.anyio
async def test_summary_stats_sub_dict_present(client):
    """The 'stats' sub-dict inside /api/summary must have the five stat keys."""
    r = await client.get("/api/summary")
    stats = r.json()["stats"]
    for key in ("active_disruptions", "shipments_at_risk", "idle_fleet",
                "cold_chain_excursions", "critical_excursions"):
        assert key in stats, f"stats sub-dict missing key: {key}"


@pytest.mark.anyio
async def test_summary_fallback_without_credentials(client, monkeypatch):
    """
    Without WATSONX credentials in the test env, ai_generated must be False.
    This also verifies the endpoint still returns 200 (not 500).
    """
    # Tests run without real credentials; the environment should already lack them.
    # Explicitly ensure they are absent to make the test deterministic.
    for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        os.environ.pop(var, None)

    r = await client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["ai_generated"] is False


@pytest.mark.anyio
async def test_summary_fallback_summary_non_empty(client):
    """Fallback summary text must be non-empty."""
    for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        os.environ.pop(var, None)

    r = await client.get("/api/summary")
    data = r.json()
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 20


@pytest.mark.anyio
async def test_summary_model_id_none_on_fallback(client):
    """model_id must be null/None when falling back."""
    for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        os.environ.pop(var, None)

    r = await client.get("/api/summary")
    data = r.json()
    assert data["model_id"] is None


@pytest.mark.anyio
async def test_summary_stats_consistent_with_stats_endpoint(client):
    """stats sub-dict in /api/summary must match /api/summary/stats."""
    r_stats = await client.get("/api/summary/stats")
    r_summary = await client.get("/api/summary")
    stats_direct = r_stats.json()
    stats_embedded = r_summary.json()["stats"]
    for key in ("active_disruptions", "shipments_at_risk", "idle_fleet",
                "cold_chain_excursions", "critical_excursions"):
        assert stats_direct[key] == stats_embedded[key], (
            f"Mismatch on {key}: stats endpoint={stats_direct[key]}, "
            f"summary embedded={stats_embedded[key]}"
        )


@pytest.mark.anyio
async def test_summary_fallback_contains_disruption_count(client):
    """Fallback summary text must embed the real active_disruptions count."""
    for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
        os.environ.pop(var, None)

    r_stats = await client.get("/api/summary/stats")
    active = r_stats.json()["active_disruptions"]

    r_summary = await client.get("/api/summary")
    summary_text = r_summary.json()["summary"]
    assert str(active) in summary_text


@pytest.mark.anyio
async def test_summary_with_mocked_watsonx(client, monkeypatch):
    """
    With mocked watsonx credentials and mocked SDK, ai_generated must be True
    and the returned summary must be the mocked text.
    """
    monkeypatch.setenv("WATSONX_API_KEY", "mock-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "mock-project")
    monkeypatch.setenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    monkeypatch.setenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct")

    sentinel = "SENTINEL_GENERATED_TEXT_PHASE4"

    with (
        patch("services.watsonx_client.Credentials"),
        patch("services.watsonx_client.ModelInference") as mock_mi,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_text.return_value = sentinel
        mock_mi.return_value = mock_instance

        r = await client.get("/api/summary")

    assert r.status_code == 200
    data = r.json()
    assert data["ai_generated"] is True
    assert data["summary"] == sentinel
    assert data["model_id"] == "ibm/granite-3-8b-instruct"


@pytest.mark.anyio
async def test_summary_api_failure_graceful_fallback(client, monkeypatch):
    """If the SDK raises during the HTTP request, the endpoint must still return 200."""
    monkeypatch.setenv("WATSONX_API_KEY", "some-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "some-project")

    with (
        patch("services.watsonx_client.Credentials"),
        patch("services.watsonx_client.ModelInference") as mock_mi,
    ):
        mock_instance = MagicMock()
        mock_instance.generate_text.side_effect = ConnectionError("network error")
        mock_mi.return_value = mock_instance

        r = await client.get("/api/summary")

    assert r.status_code == 200
    data = r.json()
    assert data["ai_generated"] is False
    assert isinstance(data["summary"], str)
    assert len(data["summary"]) > 0


# ===========================================================================
# C — Phase 2 + Phase 3 regression
# ===========================================================================

@pytest.mark.anyio
async def test_regression_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_regression_disruptions(client):
    r = await client.get("/api/disruptions")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_regression_shipments(client):
    r = await client.get("/api/shipments")
    assert r.status_code == 200
    assert r.json()["total"] == 15


@pytest.mark.anyio
async def test_regression_fleet(client):
    r = await client.get("/api/fleet")
    assert r.status_code == 200
    assert r.json()["total"] == 10


@pytest.mark.anyio
async def test_regression_cold_chain(client):
    r = await client.get("/api/cold-chain")
    assert r.status_code == 200
    assert r.json()["total"] == 11
