"""
Magnum S&OP FastAPI Server
--------------------------
Exposes the pipeline data as REST endpoints for the generative dashboard.

The pipeline runs once on startup and results are cached in memory.
Re-use the same compute_results() pattern from dashboard.py.

Run with:
  uv run uvicorn server:app --reload --port 8000
"""

import math
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from pipeline import extract, transform, consolidate, calculate
from ppt_export import generate_pptx


# ---------------------------------------------------------------------------
# Startup: load raw data and run the full pipeline once
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {}


def _load_pipeline() -> None:
    print("\n=== Loading pipeline data for API server ===\n")

    raw = {
        "conv_table": extract.load_conversion_table(),
        "attain_table": extract.load_attainment_table(),
        "tmicc": extract.load_actual_supply_tmicc(),
        "cm": extract.load_actual_supply_cm(),
        "rr": extract.load_rr_supply(),
        "manual_supply": extract.load_manual_supply_adjustments(),
        "ptg_baseline": extract.load_ptg_2026_baseline(),
        "inventory": extract.load_actual_inventory(),
        "demand": extract.load_demand(),
        "inv_seeds": extract.load_inv_seeds(),
        "actual_inv": extract.load_actual_inv_by_tech(),
        "client_doh": extract.load_client_doh_and_targets(),
    }

    supply_monthly = transform.prepare_supply(
        raw["tmicc"], raw["cm"], raw["rr"],
        raw["conv_table"], raw["attain_table"],
        manual_df=raw["manual_supply"],
    )
    demand_monthly = transform.prepare_demand(raw["demand"], raw["conv_table"])
    inventory_monthly = transform.prepare_inventory(raw["inventory"], raw["conv_table"])

    master = consolidate.build_master_view(
        supply_monthly, demand_monthly, inventory_monthly,
        ptg_2026_baseline=raw["ptg_baseline"],
    )
    site_supply = consolidate.build_site_supply_view(supply_monthly)

    master = calculate.project_inventory(
        master, starting_inv=raw["inv_seeds"], actual_inv=raw["actual_inv"],
    )
    master = calculate.compute_matdi(master, client_doh_data=raw["client_doh"])
    bandwidth = calculate.compute_bandwidth(master, client_doh_data=raw["client_doh"])
    matdi_vs_target = calculate.compare_to_matdi_targets(master)

    _cache["master"] = master
    _cache["site_supply"] = site_supply
    _cache["bandwidth"] = bandwidth
    _cache["matdi_vs_target"] = matdi_vs_target

    print("\n=== Pipeline loaded and cached ===\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_pipeline()
    yield


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Magnum S&OP API",
    description="Pipeline data endpoints for the generative dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _clean(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None so JSON serialisation never fails."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _df_to_records(df) -> list[dict]:
    return _clean(df.to_dict(orient="records"))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/data/technologies")
def get_technologies():
    """List of all technology names available in the pipeline."""
    master = _cache.get("master")
    if master is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")
    techs = sorted(master["main_tech"].unique().tolist())
    return {"technologies": techs}


@app.get("/api/data/season-readiness")
def get_season_readiness():
    """Bandwidth and season readiness traffic-light for every technology."""
    bandwidth = _cache.get("bandwidth")
    if bandwidth is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")
    records = _df_to_records(bandwidth)
    summary = {
        "green": int((bandwidth["season_readiness"] == "Green").sum()),
        "yellow": int((bandwidth["season_readiness"] == "Yellow").sum()),
        "red": int((bandwidth["season_readiness"] == "Red").sum()),
    }
    return {"summary": summary, "items": records}


@app.get("/api/data/rccp/{tech}")
def get_rccp(tech: str):
    """
    Monthly supply, demand, inventory, DOH for a single technology.
    Returns rows sorted by month.
    """
    master = _cache.get("master")
    if master is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    techs = master["main_tech"].unique().tolist()
    if tech not in techs:
        raise HTTPException(
            status_code=404,
            detail=f"Technology '{tech}' not found. Available: {sorted(techs)}",
        )

    inv_col = "projected_inv_cases" if "projected_inv_cases" in master.columns else "inv_cases"
    cols = ["month", "supply_cases", "demand_cases", inv_col]
    if "doh" in master.columns:
        cols.append("doh")
    if "matdi" in master.columns:
        cols.append("matdi")

    df = master[master["main_tech"] == tech][cols].copy()
    df = df.sort_values("month").reset_index(drop=True)
    if inv_col != "projected_inv_cases":
        df = df.rename(columns={inv_col: "projected_inv_cases"})

    bandwidth = _cache.get("bandwidth")
    tech_bw = bandwidth[bandwidth["main_tech"] == tech] if bandwidth is not None else None
    bw_info = _df_to_records(tech_bw)[0] if (tech_bw is not None and len(tech_bw) > 0) else {}

    return {
        "tech": tech,
        "bandwidth_info": bw_info,
        "monthly_data": _df_to_records(df),
    }


@app.get("/api/data/tonnage-by-site")
def get_tonnage_by_site():
    """Monthly liton tonnage grouped by manufacturing site."""
    site_supply = _cache.get("site_supply")
    if site_supply is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    import pandas as pd
    tonnage = site_supply.groupby(["site_name", "month"], as_index=False)["supply_litons"].sum()
    tonnage = tonnage.sort_values(["site_name", "month"]).reset_index(drop=True)

    sites = sorted(tonnage["site_name"].unique().tolist())
    months = sorted(tonnage["month"].unique().tolist())
    total = float(tonnage["supply_litons"].sum())

    return {
        "total_litons": _clean(total),
        "sites": sites,
        "months": months,
        "rows": _df_to_records(tonnage),
    }


@app.get("/api/data/pallet-position")
def get_pallet_position():
    """Total pallet position (all technologies) by month."""
    master = _cache.get("master")
    if master is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    pallet_total = master.groupby("month", as_index=False)["supply_pallets"].sum()
    pallet_total = pallet_total.sort_values("month").reset_index(drop=True)

    peak_idx = int(pallet_total["supply_pallets"].idxmax())
    peak_month = pallet_total.loc[peak_idx, "month"]
    peak_pallets = float(pallet_total.loc[peak_idx, "supply_pallets"])

    return {
        "peak_month": peak_month,
        "peak_pallets": _clean(peak_pallets),
        "monthly_data": _df_to_records(pallet_total),
    }


@app.get("/api/data/matdi-comparison")
def get_matdi_comparison():
    """MATDI vs target at Apr / Aug / Dec checkpoints for every technology."""
    matdi_vs_target = _cache.get("matdi_vs_target")
    if matdi_vs_target is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    on_track = int((matdi_vs_target["status"] == "On Track").sum())
    at_risk = int((matdi_vs_target["status"] == "At Risk").sum())

    return {
        "summary": {"on_track": on_track, "at_risk": at_risk},
        "rows": _df_to_records(matdi_vs_target),
    }


@app.get("/api/data/summary-metrics")
def get_summary_metrics():
    """High-level KPIs across the full planning horizon."""
    master = _cache.get("master")
    bandwidth = _cache.get("bandwidth")
    if master is None or bandwidth is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    inv_col = "projected_inv_cases" if "projected_inv_cases" in master.columns else "inv_cases"

    total_demand = float(master["demand_cases"].sum())
    total_supply = float(master["supply_cases"].sum())
    peak_inv = float(master[inv_col].max())
    peak_inv_month = master.loc[master[inv_col].idxmax(), "month"]
    num_techs = int(master["main_tech"].nunique())

    green_n = int((bandwidth["season_readiness"] == "Green").sum())
    yellow_n = int((bandwidth["season_readiness"] == "Yellow").sum())
    red_n = int((bandwidth["season_readiness"] == "Red").sum())

    avg_bandwidth = float(bandwidth["bandwidth"].mean())

    return _clean({
        "total_demand_cases": total_demand,
        "total_supply_cases": total_supply,
        "supply_demand_ratio": total_supply / total_demand if total_demand > 0 else None,
        "peak_inventory_cases": peak_inv,
        "peak_inventory_month": peak_inv_month,
        "num_technologies": num_techs,
        "season_readiness": {
            "green": green_n,
            "yellow": yellow_n,
            "red": red_n,
            "avg_bandwidth_pct": round(avg_bandwidth * 100, 1),
        },
    })


# ---------------------------------------------------------------------------
# PPT Export
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    slides: list[str] | None = None


@app.post("/api/export/ppt")
def export_ppt(request: ExportRequest):
    """Generate a PowerPoint deck from the cached pipeline data."""
    master = _cache.get("master")
    bandwidth = _cache.get("bandwidth")
    matdi_vs_target = _cache.get("matdi_vs_target")
    site_supply = _cache.get("site_supply")

    if master is None or bandwidth is None:
        raise HTTPException(status_code=503, detail="Pipeline not loaded")

    pptx_bytes = generate_pptx(
        master=master,
        bandwidth=bandwidth,
        matdi_vs_target=matdi_vs_target,
        site_supply=site_supply,
        slides=request.slides,
    )

    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": "attachment; filename=Magnum_SOP_2026.pptx",
        },
    )
