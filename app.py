import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF


# -----------------------
# Helpers
# -----------------------
def money(v: float) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "R0"
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

# ---- NEW: Built Heritage Overlay ----
st.sidebar.subheader("🏛️ Overlays")
heritage_on = st.sidebar.checkbox("Built Heritage Overlay (ON)", value=False)

# Sensible defaults; tweak as needed
heritage_bulk_reduction = st.sidebar.slider("Heritage bulk reduction (%)", 0, 50, 15, step=1)
heritage_cost_uplift = st.sidebar.slider("Heritage construction cost uplift (%)", 0, 50, 10, step=1)
heritage_fees_uplift = st.sidebar.slider("Heritage professional fees uplift (%)", 0, 50, 5, step=1)
heritage_profit_uplift = st.sidebar.slider("Heritage profit uplift (%)", 0, 20, 2, step=1)


# -----------------------
# Calculation Engine
# -----------------------
def calculate_metrics(
    land, ff, bonus, ih, m_price, c_cost,
    heritage_on=False,
    heritage_bulk_reduction=0,
    heritage_cost_uplift=0,
    heritage_fees_uplift=0,
    he
