"""
FLEETIQ Bob MCP Server package.

Exposes 6 MCP tools to IBM Bob for natural-language querying of FLEETIQ data:
  get_active_disruptions        — active/monitoring disruptions with severity
  get_affected_shipments        — at-risk shipments (filterable by disruption_id/severity)
  get_idle_fleet                — redeployable vehicles, optionally near a region
  get_cold_chain_alerts         — temperature excursions ranked by severity
  get_ai_summary                — IBM watsonx.ai Granite operational summary
  get_shipment_recommendations  — rerouting/carrier options for a tracking number
"""
