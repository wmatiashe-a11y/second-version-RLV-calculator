import streamlit as st
import pandas as pd
from fpdf import FPDF
import io

# --- CONFIG & STYLING ---
st.set_page_config(page_title="CPT Property Redevelopment Calc", layout="wide")

# --- DATA PRESETS ---
ZONING = {
    "GR2 (Residential - 1.0 FF)": {"ff": 1.0},
    "GR4 (High Density - 1.5 FF)": {"ff": 1.5},
    "MU1 (Mixed Use - 1.5 FF)": {"ff": 1.5},
    "MU2 (High Density Mixed - 4.0 FF)": {"ff": 4.0},
    "GB7 (CBD/High Rise - 12.0 FF)": {"ff": 12.0},
}
DC_RATE = 514.10
IH_CAP_PRICE = 15000

# --- SIDEBAR INPUTS ---
st.sidebar.title("🛠️ Development Inputs")
land_size = st.sidebar.number_input("Land Area (m²)", value=1000)
zone_choice = st.sidebar.selectbox("Zoning Preset", list(ZONING.keys()))
parking_zone = st.sidebar.radio("Parking Zone", ["Standard", "PT1 (Reduced)", "PT2 (Zero)"])
market_price = st.sidebar.slider("Market Sales Price (R/m²)", 20000, 80000, 45000)
const_cost_base = st.sidebar.slider("Base Construction (R/m²)", 12000, 25000, 17000)
ih_req = st.sidebar.slider("Inclusionary Housing (%)", 0, 30, 20)
density_bonus = st.sidebar.slider("Density Bonus (%)", 0, 100, 20)

# --- CALCULATION ENGINE ---
def calculate_metrics(land, ff, bonus, ih, m_price, c_cost):
    total_bulk = (land * ff) * (1 + (bonus / 100))
    ih_bulk = total_bulk * (ih / 100)
    market_bulk = total_bulk - ih_bulk
    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)
    dev_charges = market_bulk * DC_RATE
    construction = total_bulk * c_cost
    fees = construction * 0.125
    profit_target = gdv * 0.20
    rlv = gdv - construction - dev_charges - fees - profit_target
    return rlv, total_bulk, dev_charges, gdv, ih_bulk

# Logic for Parking Cost Adjustment
if parking_zone == "PT2 (Zero)":
    const_cost = const_cost_base * 0.85
elif parking_zone == "PT1 (Reduced)":
    const_cost = const_cost_base * 0.95
else:
    const_cost = const_cost_base

ff_val = ZONING[zone_choice]["ff"]
rlv, bulk, dcs, gdv, ih_bulk = calculate_metrics(land_size, ff_val, density_bonus, ih_req, market_price, const_cost)

# --- PDF GENERATION FUNCTION ---
def create_pdf(rlv, bulk, dcs, gdv, ih_req, bonus, zone, p_zone):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, "Site Feasibility Report: Cape Town Redevelopment", ln=True, align="C")
    pdf.ln(10)
    
    # Site Details Table
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 10, "1. Site & Policy Parameters", ln=True)
    pdf.set_font("Arial", "", 10)
    pdf.cell(95, 8, f"Zoning: {zone}", border=1)
    pdf.cell(95, 8, f"Parking Zone: {p_zone}", border=1, ln=True)
    pdf.cell(95, 8, f"Inclusionary Housing: {ih_req}%", border=1)
    pdf.cell(95, 8, f"Density Bonus: +{bonus}%", border=1, ln=True)
    pdf.ln(5)
    
    # Financial Results
    pdf.set_font("Arial", "B", 12)
    pdf.cell(190, 10, "2. Financial Summary", ln=True)
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 128, 0) # Green
    pdf.cell(190, 12, f"RESIDUAL LAND VALUE: ZAR {rlv:,.2f}", border=1, ln=True, align="C")
    
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(95, 8, f"Gross Development Value (GDV):", border=1)
    pdf.cell(95, 8, f"ZAR {gdv:,.2f}", border=1, ln=True)
    pdf.cell(95, 8, f"Total Allowable Bulk:", border=1)
    pdf.cell(95, 8, f"{bulk:,.2f} m2", border=1, ln=True)
    pdf.cell(95, 8, f"Development Charges (Payable):", border=1)
    pdf.cell(95, 8, f"ZAR {dcs:,.2f}", border=1, ln=True)
    
    pdf.ln(10)
    pdf.set_font("Arial", "I", 8)
    pdf.multi_cell(190, 5, "Disclaimer: This report is a high-level residual land value estimate based on user inputs and current City of Cape Town DC guidelines. It does not constitute a formal valuation.")
    
    return pdf.output()

# --- UI DISPLAY ---
st.title("Cape Town Residual Land Value Calculator")

# Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Residual Land Value", f"R {max(0, rlv/1e6):.2f}M")
c2.metric("Total Bulk (GBA)", f"{bulk:,.0f} m²")
c3.metric("Dev Charges", f"R {dcs/1e3:,.0f}k")
c4.metric("Total GDV", f"R {gdv/1e6:.2f}M")

# PDF Download Button in Sidebar
pdf_bytes = create_pdf(rlv, bulk, dcs, gdv, ih_req, density_bonus, zone_choice, parking_zone)
st.sidebar.download_button(
    label="📥 Download Feasibility Report (PDF)",
    data=pdf_bytes,
    file_name="CPT_Feasibility_Report.pdf",
    mime="application/pdf",
)

# --- SENSITIVITY TABLE ---
st.subheader("Sensitivity: IH Requirement vs Density Bonus")
matrix = []
ih_levels = [0, 10, 20, 30]
bonus_levels = [0, 20, 40, 60, 80, 100]

for ih in ih_levels:
    row = []
    for b in bonus_levels:
        val, _, _, _, _ = calculate_metrics(land_size, ff_val, b, ih, market_price, const_cost)
        row.append(round(val / 1e6, 2))
    matrix.append(row)

df_map = pd.DataFrame(matrix, index=[f"{i}% IH" for i in ih_levels], columns=[f"+{b}% Bonus" for b in bonus_levels])
st.dataframe(df_map.style.background_gradient(cmap='RdYlGn', axis=None))
