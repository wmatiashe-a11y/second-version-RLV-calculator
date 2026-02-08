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
# Built Heritage Overlay (HPO/HPOZ)
# -----------------------
st.sidebar.subheader("🏛️ Built Heritage (HPO / HPOZ)")

heritage_on = st.sidebar.checkbox(
    "Site is within a Heritage Protection Overlay (HPO/HPOZ)",
    value=False,
    help=(
        "HPO/HPOZ is an overlay control area. In practice, it often triggers additional approvals and conditions. "
        "This calculator conservatively assumes bonus bulk is not achievable unless approvals are secured."
    ),
)

heritage_approvals_secured = st.sidebar.checkbox(
    "Assume heritage approvals secured for additional bulk/bonus",
    value=False,
    help="If unticked and HPO/HPOZ applies, density bonus is treated as 0.",
)

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
    # Policy-aligned conservative assumption:
    # If HPO/HPOZ applies and approvals are NOT secured, do not assume density bonus is achievable.
    effective_bonus = bonus
    if heritage_on and not heritage_approvals_secured:
        effective_bonus = 0

    total_bulk = (land * ff) * (1 + (effective_bonus / 100.0))

    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)

    # Development charges assumed on market bulk (consistent with your original logic)
    dev_charges = market_bulk * DC_RATE

    # Heritage uplifts (simple, user-controlled)
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
# PDF Generation (FPDF2 compliant)
# -----------------------
@st.cache_data(show_spinner=False)
def create_pdf_bytes(
    land_size, zone_choice, ff_val, parking_zone,
    market_price, const_cost, ih_req, density_bonus,
    base_rlv, ih_rlv, ihb_rlv,
    heritage_on, heritage_approvals_secured,
    heritage_cost_uplift, heritage_fees_uplift, heritage_profit_uplift,
) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        190, 10,
        "Site Feasibility Report: Cape Town Redevelopment",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        align="C",
    )
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Inputs", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Land area: {land_size} m²", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Zoning: {zone_choice} (FAR={ff_val})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Parking zone: {parking_zone}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Market price: {money(market_price)}/m²", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Construction cost used: {money(const_cost)}/m²", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"IH requirement: {ih_req}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Density bonus (requested): +{density_bonus}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Built Heritage (HPO/HPOZ)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"HPO/HPOZ applies: {'YES' if heritage_on else 'NO'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(
        190, 7,
        f"Approvals secured for additional bulk/bonus: {'YES' if heritage_approvals_secured else 'NO'}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    if heritage_on and not heritage_approvals_secured:
        pdf.cell(
            190, 7,
            "Note: Density bonus treated as 0% (conservative assumption under HPO/HPOZ without approvals).",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
    pdf.cell(190, 7, f"Cost uplift: {heritage_cost_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Fees uplift: {heritage_fees_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Profit/risk uplift: {heritage_profit_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Scenario Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Base (No IH, No Bonus) RLV: {money(base_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"IH Only RLV: {money(ih_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"IH + Bonus RLV: {money(ihb_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return pdf.output(dest="S").encode("latin-1", errors="replace")


pdf_data = create_pdf_bytes(
    land_size, zone_choice, ff_val, parking_zone,
    market_price, const_cost, ih_req, density_bonus,
    base_rlv, ih_rlv, ihb_rlv,
    heritage_on, heritage_approvals_secured,
    heritage_cost_uplift, heritage_fees_uplift, heritage_profit_uplift,
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

c1, c2, c3, c4 = st.columns(4)
c1.metric("Residual Land Value (IH+Bonus)", money(rlv))
c2.metric("Total Bulk (m²)", f"{bulk:,.0f}")
c3.metric("Dev Charges", money(dcs))
c4.metric("Total GDV", money(gdv))

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
# Sensitivity (heritage-aware heatmap)
# -----------------------
st.subheader("Sensitivity: IH Requirement vs Density Bonus (Heritage-aware)")

ih_levels = [0, 10, 20, 30]
bonus_levels = [0, 20, 40, 60, 80, 100]

matrix = []
for ih in ih_levels:
    row = []
    for b in bonus_levels:
        val, _, _, _, _ = calculate_metrics(
            land_size, ff_val, b, ih, market_price, const_cost,
            heritage_on=heritage_on,
            heritage_approvals_secured=heritage_approvals_secured,
            heritage_cost_uplift=heritage_cost_uplift,
            heritage_fees_uplift=heritage_fees_uplift,
            heritage_profit_uplift=heritage_profit_uplift,
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
    xaxis_title="Density Bonus (requested; may be constrained by HPO/HPOZ)",
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
