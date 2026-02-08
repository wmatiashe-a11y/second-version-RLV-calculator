import os
import tempfile
from dataclasses import dataclass

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF
import streamlit.components.v1 as components


# -----------------------
# Helpers
# -----------------------
def money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}R{abs(v):,.0f}"


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# -----------------------
# CONFIG
# -----------------------
st.set_page_config(page_title="CPT Property Redevelopment Calc", layout="wide")

ZONING = {
    "GR2 (Residential - 1.0 FF)": {"ff": 1.0},
    "GR4 (High Density - 1.5 FF)": {"ff": 1.5},
    "MU1 (Mixed Use - 1.5 FF)": {"ff": 1.5},
    "MU2 (High Density Mixed - 4.0 FF)": {"ff": 4.0},
    "GB7 (CBD/High Rise - 12.0 FF)": {"ff": 12.0},
}

DC_RATE = 514.10
IH_CAP_PRICE = 15000

# City of Cape Town Map Viewer (EGIS Viewer / CityMap public viewer)
CITYMAP_VIEWER_URL = "https://citymaps.capetown.gov.za/EGISViewer/"


# -----------------------
# Heritage overlay model
# -----------------------
@dataclass(frozen=True)
class HeritageOverlay:
    enabled: bool
    bulk_reduction_pct: float      # reduces achievable bulk (a proxy for restrictions)
    cost_uplift_pct: float         # increases construction costs (specialist methods/materials)
    fees_uplift_pct: float         # increases professional fees
    profit_uplift_pct: float       # increases required profit/contingency due to approval risk


def apply_heritage_overlay(
    total_bulk: float,
    base_cost_sqm: float,
    base_fees_rate: float,
    base_profit_rate: float,
    overlay: HeritageOverlay,
) -> tuple[float, float, float, float]:
    """
    Returns:
      (adj_total_bulk, adj_cost_sqm, adj_fees_rate, adj_profit_rate)
    """
    if not overlay.enabled:
        return total_bulk, base_cost_sqm, base_fees_rate, base_profit_rate

    adj_bulk = total_bulk * (1.0 - overlay.bulk_reduction_pct / 100.0)
    adj_cost = base_cost_sqm * (1.0 + overlay.cost_uplift_pct / 100.0)
    adj_fees = base_fees_rate * (1.0 + overlay.fees_uplift_pct / 100.0)
    adj_profit = base_profit_rate * (1.0 + overlay.profit_uplift_pct / 100.0)
    return adj_bulk, adj_cost, adj_fees, adj_profit


# -----------------------
# Inputs (Sidebar)
# -----------------------
st.sidebar.title("🛠️ Development Inputs")

# Property Quick-Profile (CityMap)
st.sidebar.subheader("🏠 Property Quick-Profile (CityMap)")
q = st.sidebar.text_input(
    "Search / Address / Erf (use CityMap Viewer)",
    placeholder="e.g. '123 Main Road, Sea Point' or 'Erf 12345'",
)
st.sidebar.caption("Tip: Use the City of Cape Town Map Viewer to identify the erf and confirm land area / constraints.")
if q.strip():
    st.sidebar.markdown(
        f"Open CityMap Viewer and search for: **{q.strip()}**  \n"
        f"➡️ {CITYMAP_VIEWER_URL}"
    )
else:
    st.sidebar.markdown(f"➡️ {CITYMAP_VIEWER_URL}")

land_size = st.sidebar.number_input("Land Area (m²)", min_value=1, value=1000, step=50)

zone_choice = st.sidebar.selectbox("Zoning Preset", list(ZONING.keys()))
parking_zone = st.sidebar.radio("Parking Zone", ["Standard", "PT1 (Reduced)", "PT2 (Zero)"])

market_price = st.sidebar.slider("Market Sales Price (R/m²)", 20000, 80000, 45000, step=500)
const_cost_base = st.sidebar.slider("Base Construction (R/m²)", 12000, 25000, 17000, step=250)

ih_req = st.sidebar.slider("Inclusionary Housing (%)", 0, 30, 20, step=1)
density_bonus = st.sidebar.slider("Density Bonus (%)", 0, 100, 20, step=5)

st.sidebar.divider()
st.sidebar.subheader("🏛️ Built Heritage Overlay (City of Cape Town)")

heritage_enabled = st.sidebar.checkbox("Apply Built Heritage overlay adjustments", value=False)
st.sidebar.caption(
    "This is a **feasibility proxy** for Heritage Protection Overlay / heritage constraints: "
    "reduced developable bulk + cost/fees/risk uplifts. Tune to match your sub-area/precedent."
)

heritage_bulk_reduction = st.sidebar.slider("Bulk reduction (%)", 0, 40, 10, step=1, disabled=not heritage_enabled)
heritage_cost_uplift = st.sidebar.slider("Construction cost uplift (%)", 0, 30, 8, step=1, disabled=not heritage_enabled)
heritage_fees_uplift = st.sidebar.slider("Fees uplift (%)", 0, 30, 5, step=1, disabled=not heritage_enabled)
heritage_profit_uplift = st.sidebar.slider("Profit/risk uplift (%)", 0, 30, 5, step=1, disabled=not heritage_enabled)

heritage_for_sensitivity = st.sidebar.checkbox(
    "Include Built Heritage overlay in sensitivity analysis",
    value=True,
    disabled=not heritage_enabled,
)

overlay = HeritageOverlay(
    enabled=heritage_enabled,
    bulk_reduction_pct=float(heritage_bulk_reduction),
    cost_uplift_pct=float(heritage_cost_uplift),
    fees_uplift_pct=float(heritage_fees_uplift),
    profit_uplift_pct=float(heritage_profit_uplift),
)

# -----------------------
# Calculation Engine
# -----------------------
def calculate_metrics(
    land: float,
    ff: float,
    bonus: float,
    ih: float,
    m_price: float,
    c_cost_sqm: float,
    overlay_obj: HeritageOverlay,
) -> tuple[float, float, float, float, float]:
    """
    Returns:
      (rlv, total_bulk, dev_charges, gdv, ih_bulk)
    """
    # Base bulk
    total_bulk_raw = (land * ff) * (1 + (bonus / 100.0))

    # Rates
    base_fees_rate = 0.125
    base_profit_rate = 0.20

    # Apply heritage overlay to bulk + cost/fees/profit rates
    total_bulk, adj_cost_sqm, fees_rate, profit_rate = apply_heritage_overlay(
        total_bulk=total_bulk_raw,
        base_cost_sqm=c_cost_sqm,
        base_fees_rate=base_fees_rate,
        base_profit_rate=base_profit_rate,
        overlay=overlay_obj,
    )

    # IH split
    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    # Value + costs
    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)
    dev_charges = market_bulk * DC_RATE

    construction = total_bulk * adj_cost_sqm
    fees = construction * fees_rate
    profit_target = gdv * profit_rate

    rlv = gdv - construction - dev_charges - fees - profit_target
    return float(rlv), float(total_bulk), float(dev_charges), float(gdv), float(ih_bulk)


# Parking adjustment
if parking_zone == "PT2 (Zero)":
    const_cost = const_cost_base * 0.85
elif parking_zone == "PT1 (Reduced)":
    const_cost = const_cost_base * 0.95
else:
    const_cost = const_cost_base

ff_val = float(ZONING[zone_choice]["ff"])

# Scenarios (heritage applies to the dashboard if enabled)
base_rlv, base_bulk, base_dcs, base_gdv, base_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=0, m_price=market_price, c_cost_sqm=const_cost, overlay_obj=overlay
)
ih_rlv, ih_bulk0, ih_dcs, ih_gdv, ih_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=ih_req, m_price=market_price, c_cost_sqm=const_cost, overlay_obj=overlay
)
ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=density_bonus, ih=ih_req, m_price=market_price, c_cost_sqm=const_cost, overlay_obj=overlay
)

# Headline outputs (IH + Bonus)
rlv, bulk, dcs, gdv, ih_bulk = ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk


# -----------------------
# PDF Generation (robust)
# -----------------------
@st.cache_data(show_spinner=False)
def create_pdf_bytes_cached(
    land_area: float,
    zone: str,
    ff: float,
    parking: str,
    m_price: float,
    base_cost: float,
    used_cost: float,
    ih_pct: int,
    bonus_pct: int,
    heritage_on: bool,
    heritage_bulk_red: float,
    heritage_cost_upl: float,
    heritage_fees_upl: float,
    heritage_profit_upl: float,
    base_rlv_in: float,
    ih_rlv_in: float,
    ihb_rlv_in: float,
) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(190, 10, "Site Feasibility Report: Cape Town Redevelopment", ln=True, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Inputs", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Land area: {land_area:,.0f} m²", ln=True)
    pdf.cell(190, 7, f"Zoning: {zone} (FAR={ff})", ln=True)
    pdf.cell(190, 7, f"Parking zone: {parking}", ln=True)
    pdf.cell(190, 7, f"Market price: {money(m_price)}/m²", ln=True)
    pdf.cell(190, 7, f"Base construction cost: {money(base_cost)}/m²", ln=True)
    pdf.cell(190, 7, f"Construction cost used: {money(used_cost)}/m²", ln=True)
    pdf.cell(190, 7, f"IH requirement: {ih_pct}%", ln=True)
    pdf.cell(190, 7, f"Density bonus: +{bonus_pct}%", ln=True)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(190, 7, "Built Heritage overlay (proxy adjustments)", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Enabled: {'Yes' if heritage_on else 'No'}", ln=True)
    if heritage_on:
        pdf.cell(190, 7, f"Bulk reduction: {heritage_bulk_red:.0f}%", ln=True)
        pdf.cell(190, 7, f"Cost uplift: {heritage_cost_upl:.0f}%", ln=True)
        pdf.cell(190, 7, f"Fees uplift: {heritage_fees_upl:.0f}%", ln=True)
        pdf.cell(190, 7, f"Profit/risk uplift: {heritage_profit_upl:.0f}%", ln=True)

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Scenario Summary", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Base (No IH, No Bonus) RLV: {money(base_rlv_in)}", ln=True)
    pdf.cell(190, 7, f"IH Only RLV: {money(ih_rlv_in)}", ln=True)
    pdf.cell(190, 7, f"IH + Bonus RLV: {money(ihb_rlv_in)}", ln=True)

    # robust bytes via tempfile (works across fpdf/fpdf2 variants)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        pdf.output(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


pdf_data = create_pdf_bytes_cached(
    land_area=float(land_size),
    zone=zone_choice,
    ff=float(ff_val),
    parking=parking_zone,
    m_price=float(market_price),
    base_cost=float(const_cost_base),
    used_cost=float(const_cost),
    ih_pct=int(ih_req),
    bonus_pct=int(density_bonus),
    heritage_on=bool(heritage_enabled),
    heritage_bulk_red=float(heritage_bulk_reduction),
    heritage_cost_upl=float(heritage_cost_uplift),
    heritage_fees_upl=float(heritage_fees_uplift),
    heritage_profit_upl=float(heritage_profit_uplift),
    base_rlv_in=float(base_rlv),
    ih_rlv_in=float(ih_rlv),
    ihb_rlv_in=float(ihb_rlv),
)

st.sidebar.download_button(
    label="📥 Download Feasibility Report (PDF)",
    data=pdf_data,
    file_name="CPT_Feasibility_Report.pdf",
    mime="application/pdf",
    width="stretch",
)


# -----------------------
# UI Display
# -----------------------
st.title("Cape Town Residual Land Value Calculator")

# Header: Property Quick-Profile (CityMap Viewer)
with st.container(border=True):
    st.subheader("🏠 Property Quick-Profile")
    cA, cB = st.columns([2, 1])
    with cA:
        header_q = st.text_input(
            "Search / Address / Erf (City of Cape Town Map Viewer)",
            value=q,
            placeholder="Type an address or erf number, then use CityMap Viewer to identify the parcel and constraints.",
        )
        st.caption(
            "Note: The public CityMap/EGIS Viewer is used here as a *viewer*. "
            "Parcel size auto-fetch is not enabled in this build—confirm land area and constraints in CityMap, then enter Land Area (m²) in the sidebar."
        )
    with cB:
        st.link_button("Open CityMap Viewer", CITYMAP_VIEWER_URL, width="stretch")

    # Optional embedded viewer (lightweight)
    with st.expander("Open embedded CityMap Viewer (optional)", expanded=False):
        components.iframe(CITYMAP_VIEWER_URL, height=520)


# Main KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Residual Land Value (IH+Bonus)", money(rlv))
c2.metric("Total Bulk (m²)", f"{bulk:,.0f}")
c3.metric("Dev Charges", money(dcs))
c4.metric("Total GDV", money(gdv))

if heritage_enabled:
    st.info(
        "Built Heritage overlay is ON (proxy adjustments applied to bulk, costs, fees and profit/risk). "
        "Use sensitivity below to see the effect across IH and bonus combinations."
    )

st.subheader("Scenario Comparison")
sc_df = pd.DataFrame(
    [
        ["Base (No IH, No Bonus)", base_rlv, base_gdv, base_bulk, base_dcs],
        ["IH Only", ih_rlv, ih_gdv, ih_bulk0, ih_dcs],
        ["IH + Bonus", ihb_rlv, ihb_gdv, ihb_bulk, ihb_dcs],
    ],
    columns=["Scenario", "RLV", "GDV", "Bulk_m2", "DevCharges"],
)

sc_show = sc_df.copy()
sc_show["RLV"] = sc_show["RLV"].map(money)
sc_show["GDV"] = sc_show["GDV"].map(money)
sc_show["DevCharges"] = sc_show["DevCharges"].map(money)
sc_show["Bulk_m2"] = sc_show["Bulk_m2"].map(lambda x: f"{x:,.0f}")

st.dataframe(sc_show, width="stretch", hide_index=True)

st.divider()


# -----------------------
# Sensitivity (heatmap)
# -----------------------
st.subheader("Sensitivity: IH Requirement vs Density Bonus")

ih_levels = [0, 10, 20, 30]
bonus_levels = [0, 20, 40, 60, 80, 100]

overlay_for_map = overlay if (heritage_enabled and heritage_for_sensitivity) else HeritageOverlay(
    enabled=False, bulk_reduction_pct=0, cost_uplift_pct=0, fees_uplift_pct=0, profit_uplift_pct=0
)

matrix = []
for ih in ih_levels:
    row = []
    for b in bonus_levels:
        val, _, _, _, _ = calculate_metrics(
            land_size, ff_val, b, ih, market_price, const_cost, overlay_for_map
        )
        row.append(float(val))
    matrix.append(row)

df_map = pd.DataFrame(
    matrix,
    index=[f"{i}% IH" for i in ih_levels],
    columns=[f"+{b}% Bonus" for b in bonus_levels],
)

fig = go.Figure(
    data=go.Heatmap(
        z=df_map.values.astype(float),
        x=df_map.columns,
        y=df_map.index,
        colorbar=dict(title="RLV (R)"),
    )
)
fig.update_layout(
    title="RLV sensitivity heatmap (R)",
    xaxis_title="Density Bonus",
    yaxis_title="IH Requirement",
)
st.plotly_chart(fig, width="stretch")

# Table + CSV export
fmt_df = df_map.copy()
for c in fmt_df.columns:
    fmt_df[c] = fmt_df[c].map(money)

st.dataframe(fmt_df, width="stretch")

st.download_button(
    "Download Sensitivity CSV",
    data=df_map.to_csv(index=True).encode("utf-8"),
    file_name="sensitivity_ih_bonus.csv",
    mime="text/csv",
    width="stretch",
)

st.divider()


# -----------------------
# The Feasibility Lens (Bottom Tray)
# -----------------------
st.subheader("🔎 The Feasibility Lens")

# Local comps (placeholder card – you can wire to your comps DB later)
comps_note = "Recent sales in this sub-zone: R42,000/m²."

# Bulk efficiency card (simple narrative + approximate buildable bulk)
# Your model uses FAR*land*(1+bonus), but "sellable" concept isn't explicitly modeled.
approx_bulk_gr2 = land_size * ZONING["GR2 (Residential - 1.0 FF)"]["ff"]
bulk_eff_note = f"You can build ~{approx_bulk_gr2:,.0f} m² on this plot if rezoned to GR2 (before bonuses/overlays)."

# Coastal premium (proxy)
# If you want this to actually affect costs, add a coastal toggle + uplift into overlay pipeline.
coastal_note = "High-wind zone: Adding 4% to window/glazing costs."

tray1, tray2, tray3 = st.columns(3)

with tray1:
    with st.container(border=True):
        st.markdown("### 📍 Local Comps")
        st.write(comps_note)
        st.caption("Tip: Replace with your own comps feed by suburb/sub-zone.")

with tray2:
    with st.container(border=True):
        st.markdown("### 🏗️ Bulk Efficiency")
        st.write(bulk_eff_note)
        st.caption("Approximation shown. Final bulk depends on zoning, bonuses, and overlays.")

with tray3:
    with st.container(border=True):
        st.markdown("### 💨 Coastal Premium")
        st.write(coastal_note)
        st.caption("Proxy note only (not applied in the calculation yet).")
