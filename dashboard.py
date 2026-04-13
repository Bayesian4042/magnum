"""
Magnum S&OP Dashboard
---------------------
Streamlit app. Run with:
  uv run streamlit run dashboard.py

Three tabs:
  1. Season Readiness  — traffic-light overview by technology
  2. RCCP Overview     — supply / demand / inventory / DOH per tech
  3. Sites & Pallets   — tonnage by plant + total pallet position

Sidebar controls:
  - DOH Target (days)         — overrides the 45-day default
  - MATDI Targets (Apr/Aug/Dec) — overrides checkpoint inventory-day targets
  - Attainment % per tech     — what-if on production yield
  - Manual Supply Adjustments — add extra cases to any tech/month
"""

import yaml
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from pipeline import extract, transform, consolidate, calculate

CONFIG_DIR = Path(__file__).parent / "config"

# ---- Page config ----
st.set_page_config(
    page_title="Magnum S&OP Planning",
    page_icon="🍦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Minimal CSS (pills only) ----
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-card {
        border: 1px solid #444;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    .green-pill  { background:#1a4731; color:#4ade80; border-radius:20px; padding:4px 14px; font-weight:700; }
    .yellow-pill { background:#4a3b00; color:#fbbf24; border-radius:20px; padding:4px 14px; font-weight:700; }
    .red-pill    { background:#4a1a1a; color:#f87171; border-radius:20px; padding:4px 14px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

COLORS = {
    "supply": "#6366f1",
    "demand": "#f59e0b",
    "inventory": "#10b981",
    "doh": "#8b5cf6",
    "target": "#ef4444",
}

MONTHS_2026 = [f"2026-{m:02d}" for m in range(1, 13)]


# =========================================================================
# DATA LAYER — split into cached extraction + reactive computation
# =========================================================================

@st.cache_data(show_spinner="Loading data from source files…")
def load_raw_data():
    """Cached: reads all Excel source files (slow I/O, done once)."""
    return {
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


def compute_results(
    raw: dict,
    attainment_overrides: dict[str, float] | None = None,
    doh_target: float | None = None,
    matdi_target_overrides: dict[str, float] | None = None,
    manual_supply_adds: list[dict] | None = None,
):
    """
    Reactive: re-runs transform → consolidate → calculate whenever a
    sidebar control changes.  No Excel I/O — purely in-memory.
    """
    supply_monthly = transform.prepare_supply(
        raw["tmicc"], raw["cm"], raw["rr"],
        raw["conv_table"], raw["attain_table"],
        manual_df=raw["manual_supply"],
        attainment_overrides=attainment_overrides,
    )
    demand_monthly = transform.prepare_demand(raw["demand"], raw["conv_table"])
    inventory_monthly = transform.prepare_inventory(raw["inventory"], raw["conv_table"])

    master = consolidate.build_master_view(
        supply_monthly, demand_monthly, inventory_monthly,
        ptg_2026_baseline=raw["ptg_baseline"],
    )
    site_supply = consolidate.build_site_supply_view(supply_monthly)

    if manual_supply_adds:
        for add in manual_supply_adds:
            mask = (master["main_tech"] == add["main_tech"]) & (master["month"] == add["month"])
            if mask.any():
                master.loc[mask, "supply_cases"] += add["cases"]

    use_client_doh = raw["client_doh"] if doh_target is None else None

    master = calculate.project_inventory(
        master, starting_inv=raw["inv_seeds"], actual_inv=raw["actual_inv"],
    )
    master = calculate.compute_matdi(
        master, client_doh_data=use_client_doh, doh_target_override=doh_target,
    )
    bandwidth = calculate.compute_bandwidth(
        master, client_doh_data=use_client_doh, doh_target_override=doh_target,
    )
    matdi_comparison = calculate.compare_to_matdi_targets(
        master, matdi_target_overrides=matdi_target_overrides,
    )

    return master, site_supply, bandwidth, matdi_comparison


# =========================================================================
# LOAD RAW DATA (cached)
# =========================================================================
try:
    raw = load_raw_data()
    raw_loaded = True
except Exception as e:
    st.error(f"Failed to load source data: {e}")
    st.exception(e)
    raw_loaded = False

if not raw_loaded:
    st.stop()


# =========================================================================
# SIDEBAR — logo, controls
# =========================================================================
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/96/Magnum_ice_cream_logo.svg/320px-Magnum_ice_cream_logo.svg.png",
    width=120,
)
st.sidebar.markdown("## S&OP Planning 2026")
st.sidebar.divider()

# --- Load config defaults for controls ---
with open(CONFIG_DIR / "manual_adjustments.yaml") as _f:
    _config = yaml.safe_load(_f)
_default_attains = _config.get("attainment_factors", {})
_default_doh = _config.get("doh_target", 45)
_default_matdi = _config.get("matdi_targets", {"Apr": 23.68, "Aug": 17.034, "Dec": 18.9})

# Techs that appear in the attainment table (i.e. techs with supply data)
_attain_techs = sorted(raw["attain_table"]["main_tech"].unique())

# --- Control 1: DOH Target ---
st.sidebar.markdown("### DOH Target")
doh_input = st.sidebar.number_input(
    "Days on Hand target",
    min_value=10, max_value=120,
    value=_default_doh, step=1,
    help="End-of-season inventory target in days. Default is 45.",
)
doh_override = doh_input if doh_input != _default_doh else None

st.sidebar.divider()

# --- Control 2: MATDI Targets ---
matdi_overrides: dict[str, float] = {}
with st.sidebar.expander("MATDI Targets"):
    st.caption("Inventory-days targets at key checkpoint months. Techs below target are flagged 'At Risk'.")
    for label, default_val in _default_matdi.items():
        val = st.number_input(
            f"{label} target (days)",
            min_value=0.0, max_value=100.0,
            value=float(default_val), step=0.5,
            key=f"matdi_{label}",
        )
        if abs(val - default_val) > 0.01:
            matdi_overrides[label] = val

st.sidebar.divider()

# --- Control 3: Attainment % overrides ---
attainment_overrides: dict[str, float] = {}
with st.sidebar.expander("Attainment % Overrides"):
    st.caption("Adjust production yield assumptions per technology. Only forecast (RR) supply is affected.")
    for tech in _attain_techs:
        default_pct = _default_attains.get(tech, _default_attains.get("default", 0.96))
        pct = st.slider(
            tech,
            min_value=50, max_value=100,
            value=int(round(default_pct * 100)),
            step=1,
            key=f"attain_{tech}",
        )
        new_pct = pct / 100.0
        if abs(new_pct - default_pct) > 0.005:
            attainment_overrides[tech] = new_pct

st.sidebar.divider()

# --- Control 4: Manual Supply Adjustments ---
if "manual_supply_adds" not in st.session_state:
    st.session_state.manual_supply_adds = []

with st.sidebar.expander("Manual Supply Adjustments"):
    st.caption("Add extra production cases to any technology / month for what-if testing.")
    with st.form("add_supply_form", clear_on_submit=True):
        col_tech, col_month = st.columns(2)
        add_tech = col_tech.selectbox("Technology", options=_attain_techs, key="_add_tech")
        add_month = col_month.selectbox("Month", options=MONTHS_2026, key="_add_month")
        add_cases = st.number_input("Cases to add", min_value=0, value=0, step=10_000, key="_add_cases")
        submitted = st.form_submit_button("Add")
        if submitted and add_cases > 0:
            st.session_state.manual_supply_adds.append({
                "main_tech": add_tech, "month": add_month, "cases": add_cases,
            })

    if st.session_state.manual_supply_adds:
        st.dataframe(
            pd.DataFrame(st.session_state.manual_supply_adds),
            use_container_width=True, hide_index=True,
        )
        if st.button("Clear All", key="clear_supply_adds"):
            st.session_state.manual_supply_adds = []
            st.rerun()
    else:
        st.info("No manual adjustments added yet.")

st.sidebar.divider()
st.sidebar.caption("Data source: client xlsx files in `/data`")

# --- Show active overrides summary ---
n_attain_changed = len(attainment_overrides)
n_matdi_changed = len(matdi_overrides)
n_supply_adds = len(st.session_state.manual_supply_adds)
if doh_override or n_matdi_changed or n_attain_changed or n_supply_adds:
    parts = []
    if doh_override:
        parts.append(f"DOH target → {doh_input}")
    if n_matdi_changed:
        parts.append(f"{n_matdi_changed} MATDI target(s) changed")
    if n_attain_changed:
        parts.append(f"{n_attain_changed} attainment override(s)")
    if n_supply_adds:
        parts.append(f"{n_supply_adds} manual supply add(s)")
    st.sidebar.success("Active: " + " · ".join(parts))


# =========================================================================
# COMPUTE RESULTS (reactive — re-runs on every control change)
# =========================================================================
try:
    master, site_supply, bandwidth, matdi_comparison = compute_results(
        raw,
        attainment_overrides=attainment_overrides or None,
        doh_target=doh_override,
        matdi_target_overrides=matdi_overrides or None,
        manual_supply_adds=st.session_state.manual_supply_adds or None,
    )
    data_loaded = True
except Exception as e:
    st.error(f"Computation failed: {e}")
    st.exception(e)
    data_loaded = False

if not data_loaded:
    st.stop()


# ---- Helpers ----
def month_sort_key(month_str: str) -> pd.Timestamp:
    try:
        return pd.to_datetime(month_str, format="%Y-%m")
    except Exception:
        return pd.Timestamp("2099-01-01")


all_months = sorted(master["month"].unique(), key=month_sort_key)
all_techs = sorted(master["main_tech"].unique())

# ---- Header ----
st.title("Magnum S&OP Planning Dashboard")
st.caption("MRF3 2026 — Supply, demand and inventory planning")

# =========================================================================
# TAB LAYOUT — 3 tabs
# =========================================================================
tab1, tab2, tab3 = st.tabs([
    "Season Readiness",
    "RCCP Overview",
    "Sites & Pallets",
])


# =========================================================================
# TAB 1: Season Readiness
# =========================================================================
with tab1:
    st.subheader("Season Readiness")

    col_g, col_y, col_r = st.columns(3)
    green_n = (bandwidth["season_readiness"] == "Green").sum()
    yellow_n = (bandwidth["season_readiness"] == "Yellow").sum()
    red_n = (bandwidth["season_readiness"] == "Red").sum()
    col_g.metric("Green — On Track", green_n)
    col_y.metric("Yellow — Watch", yellow_n)
    col_r.metric("Red — At Risk", red_n)

    st.divider()

    bw_sorted = bandwidth.sort_values("bandwidth", ascending=False)
    cols = st.columns(4)
    for i, (_, row) in enumerate(bw_sorted.iterrows()):
        c = cols[i % 4]
        status = row["season_readiness"]
        pill = {"Green": "green-pill", "Yellow": "yellow-pill", "Red": "red-pill"}.get(status, "")
        c.markdown(f"""
        <div class="metric-card">
            <div style="font-size:0.95rem;opacity:0.7;margin-bottom:4px">{row['main_tech']}</div>
            <div style="font-size:1.5rem;font-weight:800">{row['bandwidth']:.1%}</div>
            <div style="margin-top:6px"><span class="{pill}">{status}</span></div>
        </div>
        """, unsafe_allow_html=True)


# =========================================================================
# TAB 2: RCCP Overview (core view — one tech at a time)
# =========================================================================
with tab2:
    st.subheader("Rough Cut Capacity Plan")

    selected_tech = st.selectbox(
        "Technology", options=all_techs,
        index=all_techs.index("48oz") if "48oz" in all_techs else 0,
    )

    rccp = master[master["main_tech"] == selected_tech].copy()
    rccp["month_dt"] = pd.to_datetime(rccp["month"], format="%Y-%m", errors="coerce")
    rccp = rccp.sort_values("month_dt")

    inv_col = "projected_inv_cases" if "projected_inv_cases" in rccp.columns else "inv_cases"
    doh_col = "doh" if "doh" in rccp.columns else None

    # --- Headline metrics ---
    tech_bw = bandwidth[bandwidth["main_tech"] == selected_tech]
    peak_inv = rccp[inv_col].max() if len(rccp) else 0
    aug_row = rccp[rccp["month"] == "2026-08"]
    aug_doh = aug_row[doh_col].values[0] if (doh_col and len(aug_row)) else None
    bw_val = tech_bw["bandwidth"].values[0] if len(tech_bw) else None
    bw_status = tech_bw["season_readiness"].values[0] if len(tech_bw) else "—"

    c1, c2, c3 = st.columns(3)
    c1.metric("Peak Inventory", f"{peak_inv:,.0f} cases")
    c2.metric("Aug DOH", f"{aug_doh:.1f} days" if aug_doh is not None else "—")
    c3.metric("Bandwidth", f"{bw_val:.1%} ({bw_status})" if bw_val is not None else "—")

    # --- Chart: Supply vs Demand bars + Inventory + DOH lines ---
    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Production", x=rccp["month"], y=rccp["supply_cases"],
        marker_color=COLORS["supply"], opacity=0.85,
    ))
    fig.add_trace(go.Bar(
        name="Demand", x=rccp["month"], y=rccp["demand_cases"],
        marker_color=COLORS["demand"], opacity=0.85,
    ))
    fig.add_trace(go.Scatter(
        name="Inventory", x=rccp["month"], y=rccp[inv_col],
        mode="lines+markers", line=dict(color=COLORS["inventory"], width=3),
        yaxis="y2",
    ))

    if doh_col and doh_col in rccp.columns:
        fig.add_trace(go.Scatter(
            name="DOH", x=rccp["month"], y=rccp[doh_col],
            mode="lines+markers", line=dict(color=COLORS["doh"], width=2, dash="dot"),
            yaxis="y3",
        ))

    fig.update_layout(
        title=f"{selected_tech} — Production / Demand / Inventory / DOH",
        barmode="group",
        xaxis_title="Month",
        yaxis=dict(title="Cases"),
        yaxis2=dict(title="Inventory (cases)", overlaying="y", side="right"),
        yaxis3=dict(
            title="DOH (days)", overlaying="y", side="right",
            anchor="free", position=1.0, showgrid=False,
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(r=80),
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Summary table (mirrors client's "Inv By Tech Post Attain" layout) ---
    table_cols = {"month": "Month", "supply_cases": "Production", "demand_cases": "Demand"}
    table_cols[inv_col] = "Inventory"
    if doh_col and doh_col in rccp.columns:
        table_cols[doh_col] = "DOH"
    if "matdi" in rccp.columns:
        table_cols["matdi"] = "MATDI"

    display_df = rccp[list(table_cols.keys())].rename(columns=table_cols).copy()
    for col in ["Production", "Demand", "Inventory"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
    if "DOH" in display_df.columns:
        display_df["DOH"] = display_df["DOH"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
    if "MATDI" in display_df.columns:
        display_df["MATDI"] = display_df["MATDI"].apply(lambda v: f"{v:.1f}" if pd.notna(v) and v > 0 else "—")

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- MATDI vs Target checkpoints ---
    if len(matdi_comparison) > 0:
        tech_matdi = matdi_comparison[matdi_comparison["main_tech"] == selected_tech]
        if len(tech_matdi) > 0:
            st.markdown("**MATDI vs Target at Checkpoints**")
            matdi_display = tech_matdi[["month", "projected_matdi", "target_matdi", "diff", "status"]].copy()
            matdi_display.columns = ["Month", "Projected MATDI", "Target", "Diff", "Status"]
            st.dataframe(matdi_display, use_container_width=True, hide_index=True)


# =========================================================================
# TAB 3: Sites & Pallets
# =========================================================================
with tab3:
    st.subheader("Tonnage by Site & Pallet Position")

    # --- Tonnage by site ---
    st.markdown("**Monthly Tonnage (Litons) by Manufacturing Site**")

    tonnage = site_supply.groupby(["site_name", "month"], as_index=False)["supply_litons"].sum()
    tonnage["month_dt"] = pd.to_datetime(tonnage["month"], format="%Y-%m", errors="coerce")
    tonnage = tonnage.sort_values("month_dt")

    fig_ton = px.bar(
        tonnage, x="month", y="supply_litons", color="site_name",
        labels={"supply_litons": "Litons", "month": "Month", "site_name": "Site"},
        barmode="stack",
    )
    fig_ton.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_ton, use_container_width=True)

    st.metric("Total Annual Tonnage", f"{tonnage['supply_litons'].sum():,.0f} litons")

    st.divider()

    # --- Total pallet position ---
    st.markdown("**Total Pallet Position (all technologies)**")

    pallet_total = master.groupby("month", as_index=False)["supply_pallets"].sum()
    pallet_total["month_dt"] = pd.to_datetime(pallet_total["month"], format="%Y-%m", errors="coerce")
    pallet_total = pallet_total.sort_values("month_dt")

    fig_pal = go.Figure()
    fig_pal.add_trace(go.Scatter(
        x=pallet_total["month"], y=pallet_total["supply_pallets"],
        mode="lines+markers+text",
        text=[f"{v:,.0f}" for v in pallet_total["supply_pallets"]],
        textposition="top center",
        line=dict(color=COLORS["inventory"], width=3),
    ))
    fig_pal.update_layout(
        yaxis_title="Pallets",
        xaxis_title="Month",
    )
    st.plotly_chart(fig_pal, use_container_width=True)

    peak_pallets = pallet_total["supply_pallets"].max()
    peak_month = pallet_total.loc[pallet_total["supply_pallets"].idxmax(), "month"]
    st.metric("Peak Pallets", f"{peak_pallets:,.0f}", delta=f"in {peak_month}")
