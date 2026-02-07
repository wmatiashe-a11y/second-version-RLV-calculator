import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from fpdf import FPDF


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
# Calculation Engine
# -----------------------
def calculate_metrics(land, ff, bonus, ih, m_price, c_cost):
    total_bulk = (land * ff) * (1 + (bonus / 100.0))
    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)
    dev_charges = market_bulk * DC_RATE

    construction = total_bulk * c_cost
    fees = construction * 0.125
    profit_target = gdv * 0.20

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
    land_size, ff_val, bonus=0, ih=0, m_price=market_price, c_cost=const_cost
)
ih_rlv, ih_bulk0, ih_dcs, ih_gdv, ih_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=ih_req, m_price=market_price, c_cost=const_cost
)
ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=density_bonus, ih=ih_req, m_price=market_price, c_cost=const_cost
)

# Headline outputs
rlv, bulk, dcs, gdv, ih_bulk = ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk


# -----------------------
# PDF Generation (FPDF -> bytes)
# -----------------------
def create_pdf_bytes() -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", 14)
    pdf.cell(190, 10, "Site Feasibility Report: Cape Town Redevelopment", ln=True, align="C")
    pdf.ln(6)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 8, "Inputs", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(190, 7, f"Land area: {land_size} m²", ln=True)
    pdf.cell(190, 7, f"Zoning: {zone_choice} (FAR={ff_val})", ln=True)
    pdf.cell(190, 7, f"Parking zone: {parking_zone}", ln=True)
    pdf.cell(190, 7, f"Market price: {money(market_price)}/m²", ln=True)
    pdf.cell(190, 7, f"Construction cost used: {money(const_cost)}/m²", ln=True)
    pdf.cell(190, 7, f"IH requirement: {ih_req}%", ln=True)
    pdf.cell(190, 7, f"Density bonus: +{density_bonus}%", ln=True)

    pdf.ln(6)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 8, "Scenario Summary", ln=True)
    pdf.set_font("Arial", "", 10)

    def line(title, rlv_v, gdv_v, bulk_v, dcs_v):
        pdf.set_font("Arial", "B", 10)
        pdf.cell(190, 7, title, ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(190, 6, f"RLV: {money(rlv_v)} | GDV: {money(gdv_v)} | Bulk: {bulk_v:,.0f} m² | Dev Charges: {money(dcs_v)}", ln=True)
        pdf.ln(2)

    line("Base (No IH, No Bonus)", base_rlv, base_gdv, base_bulk, base_dcs)
    line("IH Only", ih_rlv, ih_gdv, ih_bulk0, ih_dcs)
    line("IH + Bonus", ihb_rlv, ihb_gdv, ihb_bulk, ihb_dcs)

    raw = pdf.output(dest="S")
    pdf_bytes = raw if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")
    return pdf_bytes


st.sidebar.download_button(
    label="📥 Download Feasibility Report (PDF)",
    data=create_pdf_bytes(),
    file_name="CPT_Feasibility_Report.pdf",
    mime="application/pdf",
    use_container_width=True,
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

st.dataframe(sc_show, use_container_width=True, hide_index=True)

st.divider()


# -----------------------
# Sensitivity (robust heatmap)
# -----------------------
st.subheader("Sensitivity: IH Requirement vs Density Bonus")

ih_levels = [0, 10, 20, 30]
bonus_levels = [0, 20, 40, 60, 80, 100]

matrix = []
for ih in ih_levels:
    row = []
    for b in bonus_levels:
        val, _, _, _, _ = calculate_metrics(land_size, ff_val, b, ih, market_price, const_cost)
        row.append(float(val))
    matrix.append(row)

df_map = pd.DataFrame(
    matrix,
    index=[f"{i}% IH" for i in ih_levels],
    columns=[f"+{b}% Bonus" for b in bonus_levels],
)

# Heatmap with graph_objects (no px.imshow dependency)
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
st.plotly_chart(fig, use_container_width=True)

# Table (formatted) + CSV
fmt_df = df_map.copy()
for c in fmt_df.columns:
    fmt_df[c] = fmt_df[c].map(money)
st.dataframe(fmt_df, use_container_width=True)

st.download_button(
    "Download Sensitivity CSV",
    data=df_map.to_csv(index=True).encode("utf-8"),
    file_name="sensitivity_ih_bonus.csv",
    mime="text/csv",
    use_container_width=True,
)
