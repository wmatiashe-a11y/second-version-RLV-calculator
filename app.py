import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF
from fpdf.enums import XPos, YPos


# -----------------------
# Helpers
# -----------------------
def money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}R{abs(v):,.0f}"


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


# -----------------------
# Inputs (Sidebar)
# -----------------------
st.sidebar.title("🛠️ Development Inputs")

land_size = st.sidebar.number_input("Land Area (m²)", min_value=1, value=1000, step=50)
zone_choice = st.sidebar.selectbox("Zoning Preset", list(ZONING.keys()))
parking_zone = st.sidebar.radio("Parking Zone", ["Standard", "PT1 (Reduced)", "PT2 (Zero)"])

market_price = st.sidebar.slider("Market Sales Price (R/m²)", 20000, 80000, 45000, step=500)
const_cost_base = st.sidebar.slider("Base Construction (R/m²)", 12000, 25000, 17000, step=250)

ih_req = st.sidebar.slider("Inclusionary Housing (%)", 0, 30, 20, step=1)
density_bonus = st.sidebar.slider("Density Bonus (%)", 0, 100, 20, step=5)

# -----------------------
# Built Heritage (HPO/HPOZ) — City-aligned modelling
# -----------------------
st.sidebar.subheader("🏛️ Built Heritage (HPO / HPOZ)")

heritage_on = st.sidebar.checkbox(
    "Property is within a Heritage Protection Overlay (HPO/HPOZ)",
    value=False,
    help=(
        "In Cape Town, HPO/HPOZ adds overlay provisions and often triggers additional approvals. "
        "It does not automatically grant extra bulk. If approvals are not secured, bonus density should not be assumed."
    ),
)

heritage_approvals_secured = st.sidebar.checkbox(
    "Assume heritage approvals secured for additional bulk/bonus",
    value=False,
    help="If unticked, the Density Bonus is treated as not achievable under HPO/HPOZ (conservative assumption).",
)

# Simple uplift factors (keep your model lightweight but realistic)
heritage_cost_uplift = st.sidebar.slider("Heritage construction cost uplift (%)", 0, 40, 8, step=1)
heritage_fees_uplift = st.sidebar.slider("Heritage professional fees uplift (%)", 0, 60, 15, step=1)
heritage_profit_uplift = st.sidebar.slider("Heritage risk/profit uplift (%)", 0, 20, 3, step=1)


# -----------------------
# Calculation Engine
# -----------------------
def calculate_metrics(
    land, ff, bonus, ih, m_price, c_cost,
    heritage_on=False,
    heritage_approvals_secured=False,
    heritage_cost_uplift=0,
    heritage_fees_uplift=0,
    heritage_profit_uplift=0,
):
    # --- Cape Town HPO/HPOZ logic (policy-aligned, conservative) ---
    # HPO/HPOZ is an overlay with additional provisions; bonus bulk is not assumed achievable
    # unless approvals are secured.
    effective_bonus = bonus
    if heritage_on and not heritage_approvals_secured:
        effective_bonus = 0

    total_bulk = (land * ff) * (1 + (effective_bonus / 100.0))

    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)
    dev_charges = market_bulk * DC_RATE

    used_cost = c_cost * (1 + (heritage_cost_uplift / 100.0)) if heritage_on else c_cost
    construction = total_bulk * used_cost

    base_fee_rate = 0.125
    fee_rate = base_fee_rate * (1 + (heritage_fees_uplift / 100.0)) if heritage_on else base_fee_rate
    fees = construction * fee_rate

    base_profit_rate = 0.20
    profit_rate = base_profit_rate * (1 + (heritage_profit_uplift / 100.0)) if heritage_on else base_profit_rate
    profit_target = gdv * profit_rate

    rlv = gdv - construction - dev_charges - fees - profit_target
    return rlv, total_bulk, dev_charges, gdv, ih_bulk


# Parking adjustment
if parking_zone == "PT2 (Zero)":
    const_cost = const_cost_base * 0.85
elif parking_zone == "PT1 (Reduced)":
    const_cost = const_cost_base * 0.95
else:
    const_cost = const_cost_base

ff_val = ZONING[zone_choice]["ff"]

# Scenarios
base_rlv, base_bulk, base_dcs, base_gdv, base_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=0, m_price=market_price, c_cost=const_cost,
    heritage_on=heritage_on,
    heritage_approvals_secured=heritage_approvals_secured,
    heritage_cost_uplift=heritage_cost_uplift,
    heritage_fees_uplift=heritage_fees_uplift,
    heritage_profit_uplift=heritage_profit_uplift,
)
ih_rlv, ih_bulk0, ih_dcs, ih_gdv, ih_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=ih_req, m_price=market_price, c_cost=const_cost,
    heritage_on=heritage_on,
    heritage_approvals_secured=heritage_approvals_secured,
    heritage_cost_uplift=heritage_cost_uplift,
    heritage_fees_uplift=heritage_fees_uplift,
    heritage_profit_uplift=heritage_profit_uplift,
)
ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=density_bonus, ih=ih_req, m_price=market_price, c_cost=const_cost,
    heritage_on=heritage_on,
    heritage_approvals_secured=heritage_approvals_secured,
    heritage_cost_uplift=heritage_cost_uplift,
    heritage_fees_uplift=heritage_fees_uplift,
    heritage_profit_uplift=heritage_profit_uplift,
)

# Headline outputs (IH + Bonus)
rlv, bulk, dcs, gdv, ih_bulk = ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk


# -----------------------
# PDF Generation (FPDF2-sa
