"""Recall Simulation Engine API.

Provides synthetic recall scenarios and impact calculations to demonstrate
FSMA 204 response improvements with RegEngine.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.authz import require_permission
from app.disclaimers import SIMULATION_DISCLAIMER

logger = logging.getLogger("recall-simulations")


def _query_tenant_recall_metrics(tenant_id: str) -> dict | None:
    """Query real recall metrics from tenant's CTE data."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            cte_count = db.execute(text(
                "SELECT COUNT(*) FROM fsma.cte_events WHERE tenant_id = :tid"
            ), {"tid": tenant_id}).scalar() or 0
            
            if cte_count == 0:
                return None
            
            supplier_count = db.execute(text(
                "SELECT COUNT(DISTINCT supplier_id) FROM fsma.cte_events WHERE tenant_id = :tid"
            ), {"tid": tenant_id}).scalar() or 0
            
            tlc_count = db.execute(text(
                "SELECT COUNT(DISTINCT traceability_lot_code) FROM fsma.cte_events WHERE tenant_id = :tid"
            ), {"tid": tenant_id}).scalar() or 0
            
            has_export = db.execute(text(
                "SELECT COUNT(*) FROM fsma.fda_export_log WHERE tenant_id = :tid"
            ), {"tid": tenant_id}).scalar() or 0
            
            return {
                "cte_count": cte_count,
                "supplier_count": supplier_count,
                "tlc_count": tlc_count,
                "has_export": has_export > 0,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning("recall_metrics_query_failed error=%s", str(exc))
        return None

router = APIRouter(prefix="/api/v1/simulations", tags=["Recall Simulations"])


RECALL_SCENARIOS = [
    {
        "id": "romaine-ecoli",
        "name": "E. coli O157:H7 in Romaine Lettuce",
        "description": "Farm to shelf contamination trace across leafy greens distribution.",
        "contaminant": "E. coli O157:H7",
        "product_category": "Leafy Greens",
        "ftl_category": "1",
        "supply_chain_depth": 4,
        "total_lots": 47,
        "affected_lots": 12,
        "locations_involved": 23,
        "states_affected": 8,
        "estimated_cases": 34,
        "baseline_response_hours": 18,
        "baseline_data_sources": 7,
        "baseline_completeness": 0.62,
        "regengine_response_minutes": 42,
        "regengine_data_sources": 1,
        "regengine_completeness": 0.98,
    },
    {
        "id": "shrimp-sulfite",
        "name": "Undeclared Sulfites in Imported Shrimp",
        "description": "Importer and distributor chain trace for seafood allergen risk.",
        "contaminant": "Undeclared sulfites (allergen)",
        "product_category": "Seafood",
        "ftl_category": "8",
        "supply_chain_depth": 5,
        "total_lots": 89,
        "affected_lots": 23,
        "locations_involved": 41,
        "states_affected": 14,
        "estimated_cases": 67,
        "baseline_response_hours": 36,
        "baseline_data_sources": 11,
        "baseline_completeness": 0.41,
        "regengine_response_minutes": 38,
        "regengine_data_sources": 1,
        "regengine_completeness": 0.97,
    },
    {
        "id": "cheese-listeria",
        "name": "Listeria monocytogenes in Soft Cheese",
        "description": "Dairy lot tracing across multi-state retail distribution.",
        "contaminant": "Listeria monocytogenes",
        "product_category": "Dairy",
        "ftl_category": "4",
        "supply_chain_depth": 3,
        "total_lots": 31,
        "affected_lots": 8,
        "locations_involved": 15,
        "states_affected": 5,
        "estimated_cases": 12,
        "baseline_response_hours": 14,
        "baseline_data_sources": 5,
        "baseline_completeness": 0.71,
        "regengine_response_minutes": 27,
        "regengine_data_sources": 1,
        "regengine_completeness": 0.99,
    },
]


_simulation_store: dict[str, dict] = {}


class RunSimulationRequest(BaseModel):
    """Run request payload."""

    scenario_id: str = Field(..., description="Simulation scenario identifier")


def _generate_supply_chain_graph(scenario: dict) -> dict:
    location_templates = [
        "Farm",
        "Processor",
        "Distributor",
        "Retailer",
        "Restaurant",
    ]
    depth = scenario["supply_chain_depth"]
    node_count = scenario["locations_involved"]
    states = max(1, scenario["states_affected"])

    nodes = []
    links = []
    for idx in range(node_count):
        location_type = location_templates[min(idx % depth, len(location_templates) - 1)]
        affected = idx < scenario["affected_lots"]
        nodes.append(
            {
                "id": f"loc-{idx + 1}",
                "name": f"{location_type} {idx + 1}",
                "type": location_type.lower(),
                "state": f"S{(idx % states) + 1}",
                "affected": affected,
                "lot_count": max(1, scenario["total_lots"] // max(1, node_count // 2)),
                "color": "#EF4444" if affected else "#10B981",
                "size": 10 + (3 if affected else 1),
            }
        )

    for idx in range(node_count - 1):
        links.append(
            {
                "source": f"loc-{idx + 1}",
                "target": f"loc-{idx + 2}",
                "affected": idx < scenario["affected_lots"],
                "lot_codes": [f"LOT-{scenario['id'].upper()}-{idx + 1:03d}"],
            }
        )

    return {"nodes": nodes, "links": links}


def _generate_timeline(scenario: dict) -> list[dict]:
    return [
        {
            "timestamp": "2026-02-26T06:00:00Z",
            "event": "Contaminant introduced at source lot",
            "location": "Source farm",
            "status": "warning",
        },
        {
            "timestamp": "2026-02-26T14:00:00Z",
            "event": "Impacted lots shipped downstream",
            "location": "Regional distributor",
            "status": "warning",
        },
        {
            "timestamp": "2026-02-27T10:30:00Z",
            "event": "Signal detected from QA sample",
            "location": "QA laboratory",
            "status": "critical",
        },
        {
            "timestamp": "2026-02-27T11:15:00Z",
            "event": "Trace path generated and validated",
            "location": "Compliance operations center",
            "status": "success",
        },
        {
            "timestamp": "2026-02-27T11:42:00Z",
            "event": f"Recall package ready for {scenario['name']}",
            "location": "Regulatory response team",
            "status": "success",
        },
    ]


def _calculate_metrics(scenario: dict) -> dict:
    time_reduction_percent = round(
        (1 - (scenario["regengine_response_minutes"] / 60) / scenario["baseline_response_hours"]) * 100
    )

    impact_graph = _generate_supply_chain_graph(scenario)
    timeline = _generate_timeline(scenario)

    return {
        "scenario": scenario["name"],
        "contaminant": scenario["contaminant"],
        "total_lots_in_system": scenario["total_lots"],
        "affected_lots": scenario["affected_lots"],
        "affected_locations": scenario["locations_involved"],
        "states_affected": scenario["states_affected"],
        "without_regengine": {
            "response_time_hours": scenario["baseline_response_hours"],
            "data_sources_consulted": scenario["baseline_data_sources"],
            "kde_completeness": scenario["baseline_completeness"],
            "chain_verified": False,
            "export_format": "manual_spreadsheet",
        },
        "with_regengine": {
            "response_time_minutes": scenario["regengine_response_minutes"],
            "data_sources_consulted": scenario["regengine_data_sources"],
            "kde_completeness": scenario["regengine_completeness"],
            "chain_verified": True,
            "export_format": "EPCIS_2.0_XML",
            "hash_verified": True,
        },
        "time_reduction_percent": time_reduction_percent,
        "supply_chain_graph": impact_graph,
        "timeline": timeline,
    }


def _get_scenario_or_400(scenario_id: str) -> dict:
    for scenario in RECALL_SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    raise HTTPException(status_code=400, detail=f"Unknown scenario_id '{scenario_id}'")


def _get_simulation_or_404(simulation_id: str) -> dict:
    simulation = _simulation_store.get(simulation_id)
    if not simulation:
        raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found")
    return simulation


def _build_export_payload(simulation_id: str, simulation: dict) -> dict:
    return {
        "simulation_id": simulation_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "format": "application/json",
        **simulation,
    }


def _csv_rows_for_view(simulation: dict, view: str) -> list[dict]:
    metrics = simulation["metrics"]
    scenario = metrics.get("scenario", "")

    if view == "summary":
        return [
            {
                "simulation_id": simulation["id"],
                "scenario_id": simulation["scenario_id"],
                "scenario_name": scenario,
                "contaminant": metrics.get("contaminant"),
                "total_lots_in_system": metrics.get("total_lots_in_system"),
                "affected_lots": metrics.get("affected_lots"),
                "affected_locations": metrics.get("affected_locations"),
                "states_affected": metrics.get("states_affected"),
                "baseline_response_hours": metrics.get("without_regengine", {}).get("response_time_hours"),
                "regengine_response_minutes": metrics.get("with_regengine", {}).get("response_time_minutes"),
                "time_reduction_percent": metrics.get("time_reduction_percent"),
                "created_at": simulation.get("created_at"),
            }
        ]

    if view == "timeline":
        rows: list[dict] = []
        for item in metrics.get("timeline", []):
            rows.append(
                {
                    "simulation_id": simulation["id"],
                    "scenario_id": simulation["scenario_id"],
                    "scenario_name": scenario,
                    "timestamp": item.get("timestamp"),
                    "event": item.get("event"),
                    "location": item.get("location"),
                    "status": item.get("status"),
                }
            )
        return rows

    if view == "impact_graph":
        rows = []
        for link in metrics.get("supply_chain_graph", {}).get("links", []):
            rows.append(
                {
                    "simulation_id": simulation["id"],
                    "scenario_id": simulation["scenario_id"],
                    "scenario_name": scenario,
                    "source": link.get("source"),
                    "target": link.get("target"),
                    "affected": bool(link.get("affected")),
                    "lot_codes": ",".join(link.get("lot_codes", [])),
                }
            )
        return rows

    # contact_list
    rows = []
    for node in metrics.get("supply_chain_graph", {}).get("nodes", []):
        if not node.get("affected"):
            continue
        rows.append(
            {
                "simulation_id": simulation["id"],
                "scenario_id": simulation["scenario_id"],
                "scenario_name": scenario,
                "facility_id": node.get("id"),
                "facility_name": node.get("name"),
                "facility_type": node.get("type"),
                "state": node.get("state"),
                "lot_count": node.get("lot_count"),
                "notification_priority": "high",
            }
        )
    return rows


def _build_csv_export(simulation: dict, view: str) -> str:
    rows = _csv_rows_for_view(simulation, view=view)
    output = io.StringIO()
    if not rows:
        return output.getvalue()

    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


@router.get("/scenarios", summary="List available simulation scenarios")
async def list_scenarios(_auth=Depends(require_permission("simulations.read")), tenant_id: str = None):
    scenarios = [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item.get("description"),
            "product_category": item.get("product_category"),
            "contaminant": item.get("contaminant"),
            "baseline_response_hours": item.get("baseline_response_hours"),
            "regengine_response_minutes": item.get("regengine_response_minutes"),
            "is_illustrative": True,
        }
        for item in RECALL_SCENARIOS
    ]
    return {
        "scenarios": scenarios,
        "total": len(scenarios),
        "is_illustrative": True,
        "demo_disclaimer": SIMULATION_DISCLAIMER,
    }


@router.post("/run", status_code=201, summary="Run recall simulation")
async def run_recall_simulation(
    request: RunSimulationRequest,
    tenant_id: str = None,
    _auth=Depends(require_permission("simulations.write")),
):
    scenario = _get_scenario_or_400(request.scenario_id)
    metrics = _calculate_metrics(scenario)
    simulation_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # Try to compute real metrics from tenant data
    is_illustrative = True
    real_metrics = None
    if tenant_id:
        tenant_data = _query_tenant_recall_metrics(tenant_id)
        if tenant_data and tenant_data.get("cte_count", 0) > 0:
            is_illustrative = False
            real_metrics = {
                "cte_events": tenant_data["cte_count"],
                "suppliers": tenant_data["supplier_count"],
                "tlcs": tenant_data["tlc_count"],
                "export_ready": tenant_data["has_export"],
            }

    simulation_record = {
        "id": simulation_id,
        "scenario_id": scenario["id"],
        "created_at": created_at,
        "metrics": metrics,
        "is_illustrative": is_illustrative,
        "tenant_metrics": real_metrics,
        "demo_disclaimer": SIMULATION_DISCLAIMER if is_illustrative else None,
    }
    _simulation_store[simulation_id] = simulation_record

    logger.info(
        "recall_simulation_ran simulation_id=%s scenario_id=%s time_reduction_percent=%s is_illustrative=%s",
        simulation_id,
        request.scenario_id,
        metrics["time_reduction_percent"],
        is_illustrative,
    )

    return simulation_record


@router.get("/{simulation_id}", summary="Get simulation result")
async def get_simulation(
    simulation_id: str,
    _auth=Depends(require_permission("simulations.read")),
):
    return _get_simulation_or_404(simulation_id)


@router.get("/{simulation_id}/timeline", summary="Get simulation timeline")
async def get_simulation_timeline(
    simulation_id: str,
    _auth=Depends(require_permission("simulations.read")),
):
    simulation = _get_simulation_or_404(simulation_id)
    return {
        "simulation_id": simulation_id,
        "timeline": simulation["metrics"]["timeline"],
    }


@router.get("/{simulation_id}/impact-graph", summary="Get simulation impact graph")
async def get_simulation_impact_graph(
    simulation_id: str,
    _auth=Depends(require_permission("simulations.read")),
):
    simulation = _get_simulation_or_404(simulation_id)
    graph = simulation["metrics"]["supply_chain_graph"]
    return {
        "simulation_id": simulation_id,
        "nodes": graph["nodes"],
        "links": graph["links"],
    }


@router.get("/{simulation_id}/export", summary="Export simulation report")
async def export_simulation(
    simulation_id: str,
    format: Literal["json", "csv"] = Query(default="json"),
    view: Literal["summary", "timeline", "impact_graph", "contact_list"] = Query(default="summary"),
    _auth=Depends(require_permission("simulations.export")),
):
    simulation = _get_simulation_or_404(simulation_id)

    if format == "csv":
        csv_content = _build_csv_export(simulation, view=view)
        filename = f"recall_simulation_{simulation_id}_{view}.csv"
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    export_payload = _build_export_payload(simulation_id, simulation)
    export_payload["view"] = view
    return JSONResponse(
        content=export_payload,
        headers={"Content-Disposition": f'attachment; filename="recall_simulation_{simulation_id}.json"'},
    )
