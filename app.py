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
    "GR4 (High Density - 1.5 FF)": {"
