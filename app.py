import os
from urllib.parse import quote_plus

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from fpdf import FPDF
from fpdf.enums import XPos, YPos


# -----------------------
# Helpers
# -----------------------
def money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}R{abs(v):,.0f}"


def get_google_key() -> str | None:
    # Prefer Streamlit secrets; fall back to env var
    try:
        key = st.secrets.get("GOOGLE_MAPS_API_KEY")
        return key if key else None
    except Exception:
        key = os.environ.get("GOOGLE_MAPS_API_KEY")
        return key if key else None


@st.cache_data(show_spinner=False, ttl=60 * 60)
def geocode_address(address: str, api_key: str) -> dict | None:
    """Returns dict with lat, lng, formatted_address. None if not found."""
    if not address.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    res = data["results"][0]
    loc = res["geometry"]["location"]
    return {
        "lat": float(loc["lat"]),
        "lng": float(loc["lng"]),
        "formatted_address": res.get("formatted_address", address),
    }


def card_html(title: str, body: str) -> str:
    return f"""
    <div style="
        border:1px solid rgba(49,51,63,0.2);
        border-radius:12px;
        padding:12px 14px;
        background: rgba(250,250,250,0.6);
        margin-bottom:10px;">
        <div style="font-weight:700; margin-bottom:6px;">{title}</div>
        <div style="font-size:0.95rem; line-height:1.35;">{body}</div>
    </div>
    """


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
        "Overlay often triggers additional approvals/conditions. "
        "This tool conservatively assumes bonus bulk is not achievable unless approvals are secured."
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
# Coastal / Wind Premium
# -----------------------
st.sidebar.subheader("💨 Coastal / Wind")
wind_on = st.sidebar.checkbox("High-wind / coastal exposure", value=False)
wind_glazing_uplift = st.sidebar.slider("Wind uplift to construction cost (%)", 0, 15, 4, step=1)


# -----------------------
# Header: Property Quick-Profile (Main)
# -----------------------
st.markdown("## Property Quick-Profile")

google_key = get_google_key()
address = st.text_input(
    "Search / Address (optional)",
    placeholder="e.g., 1 Wale Street, Cape Town",
)

geo = None
if address and google_key:
    try:
        geo = geocode_address(address, google_key)
        if geo:
            st.caption(f"📌 {geo['formatted_address']} • Lat {geo['lat']:.5f}, Lng {geo['lng']:.5f}")
    except Exception:
        st.warning("Google geocoding failed. Check your API key, billing, and that the Geocoding API is enabled.")
elif address and not google_key:
    st.info("To enable map lookup, set GOOGLE_MAPS_API_KEY in Streamlit secrets or env vars.")

# Map preview (embed)
if geo and google_key:
    q = quote_plus(geo["formatted_address"])
    iframe = f"""
    <iframe
      width="100%"
      height="260"
      style="border:0; border-radius:12px;"
      loading="lazy"
      allowfullscreen
      referrerpolicy="no-referrer-when-downgrade"
      src="https://www.google.com/maps/embed/v1/place?key={google_key}&q={q}">
    </iframe>
    """
    st.components.v1.html(iframe, height=280)

st.caption(
    "Note: Google Maps can locate the site, but it does not provide cadastral erf/plot size. "
    "Use the sidebar Land Area input (or link a cadastral dataset later)."
)

st.divider()


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
    wind_on=False,
    wind_glazing_uplift=0,
):
    # Conservative assumption:
    # If HPO/HPOZ applies and approvals are NOT secured, do not assume density bonus is achievable.
    effective_bonus = bonus
    if heritage_on and not heritage_approvals_secured:
        effective_bonus = 0

    total_bulk = (land * ff) * (1 + (effective_bonus / 100.0))

    ih_bulk = total_bulk * (ih / 100.0)
    market_bulk = total_bulk - ih_bulk

    gdv = (market_bulk * m_price) + (ih_bulk * IH_CAP_PRICE)

    # Development charges (kept consistent with your original logic)
    dev_charges = market_bulk * DC_RATE

    # Apply uplifts
    used_cost = c_cost
    if heritage_on:
        used_cost *= (1 + (heritage_cost_uplift / 100.0))
    if wind_on:
        used_cost *= (1 + (wind_glazing_uplift / 100.0))

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
    wind_on=wind_on,
    wind_glazing_uplift=wind_glazing_uplift,
)
ih_rlv, ih_bulk0, ih_dcs, ih_gdv, ih_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=0, ih=ih_req, m_price=market_price, c_cost=const_cost,
    heritage_on=heritage_on,
    heritage_approvals_secured=heritage_approvals_secured,
    heritage_cost_uplift=heritage_cost_uplift,
    heritage_fees_uplift=heritage_fees_uplift,
    heritage_profit_uplift=heritage_profit_uplift,
    wind_on=wind_on,
    wind_glazing_uplift=wind_glazing_uplift,
)
ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk = calculate_metrics(
    land_size, ff_val, bonus=density_bonus, ih=ih_req, m_price=market_price, c_cost=const_cost,
    heritage_on=heritage_on,
    heritage_approvals_secured=heritage_approvals_secured,
    heritage_cost_uplift=heritage_cost_uplift,
    heritage_fees_uplift=heritage_fees_uplift,
    heritage_profit_uplift=heritage_profit_uplift,
    wind_on=wind_on,
    wind_glazing_uplift=wind_glazing_uplift,
)

# Headline outputs (IH + Bonus)
rlv, bulk, dcs, gdv, ih_bulk = ihb_rlv, ihb_bulk, ihb_dcs, ihb_gdv, ihb_ih_bulk


# -----------------------
# PDF Generation (FPDF2 compliant + bytearray-safe)
# -----------------------
@st.cache_data(show_spinner=False)
def create_pdf_bytes(
    land_size, zone_choice, ff_val, parking_zone,
    market_price, const_cost, ih_req, density_bonus,
    base_rlv, ih_rlv, ihb_rlv,
    heritage_on, heritage_approvals_secured,
    heritage_cost_uplift, heritage_fees_uplift, heritage_profit_uplift,
    wind_on, wind_glazing_uplift,
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
    pdf.cell(190, 7, f"Construction cost used (base): {money(const_cost)}/m²", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
            "Note: Density bonus treated as 0% (conservative under HPO/HPOZ without approvals).",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
    pdf.cell(190, 7, f"Cost uplift: {heritage_cost_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Fees uplift: {heritage_fees_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Profit/risk uplift: {heritage_profit_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Coastal / Wind", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"High-wind exposure: {'YES' if wind_on else 'NO'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"Wind uplift: {wind_glazing_uplift}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(190, 8, "Scenario Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(190, 7, f"Base (No IH, No Bonus) RLV: {money(base_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"IH Only RLV: {money(ih_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, f"IH + Bonus RLV: {money(ihb_rlv)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- IMPORTANT FIX ---
    # fpdf2 may return str OR bytearray depending on version/config
    out = pdf.output(dest="S")
    if isinstance(out, (bytes, bytearray)):
        return bytes(out)
    return out.encode("latin-1", errors="replace")


pdf_data = create_pdf_bytes(
    land_size, zone_choice, ff_val, parking_zone,
    market_price, const_cost, ih_req, density_bonus,
    base_rlv, ih_rlv, ihb_rlv,
    heritage_on, heritage_approvals_secured,
    heritage_cost_uplift, heritage_fees_uplift, heritage_profit_uplift,
    wind_on, wind_glazing_uplift,
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


# -----------------------
# The Feasibility Lens (Main Dashboard)
# -----------------------
st.markdown("## The Feasibility Lens")

# Small, tappable cards (buttons) that toggle detail cards
lens_c1, lens_c2, lens_c3 = st.columns(3)

if "show_comps" not in st.session_state:
    st.session_state.show_comps = False
if "show_bulk" not in st.session_state:
    st.session_state.show_bulk = False
if "show_wind" not in st.session_state:
    st.session_state.show_wind = False

with lens_c1:
    if st.button("📍 Local Comps", width="stretch"):
        st.session_state.show_comps = not st.session_state.show_comps
with lens_c2:
    if st.button("🏗️ Bulk Efficiency", width="stretch"):
        st.session_state.show_bulk = not st.session_state.show_bulk
with lens_c3:
    if st.button("💨 Coastal Premium", width="stretch"):
        st.session_state.show_wind = not st.session_state.show_wind

st.caption("Cape Town Context (tap a card button above to expand details)")

# Lens data
if "local_comps" not in st.session_state:
    st.session_state.local_comps = 42000

FAR_LOOKUP = {
    "SR1 (Single Residential)": 0.5,     # placeholder for lens narrative (adjust if desired)
    "GR2 (Residential)": 1.0,
    "GR4 (High Density)": 1.5,
    "MU1 (Mixed Use)": 1.5,
    "MU2 (High Density Mixed)": 4.0,
    "GB7 (CBD/High Rise)": 12.0,
}

if "current_zone" not in st.session_state:
    st.session_state.current_zone = "SR1 (Single Residential)"
if "target_zone" not in st.session_state:
    st.session_state.target_zone = "GR2 (Residential)"

# Detail tray
tray = st.container()

with tray:
    if st.session_state.show_comps:
        st.markdown(
            card_html(
                "📍 Local Comps",
                f"Recent sales in this sub-zone (placeholder): <b>{money(st.session_state.local_comps)}/m²</b>.<br>"
                f"Your input market price: <b>{money(market_price)}/m²</b>."
            ),
            unsafe_allow_html=True,
        )
        st.session_state.local_comps = int(
            st.number_input(
                "Update Local Comps (R/m²)",
                min_value=10000,
                max_value=150000,
                value=int(st.session_state.local_comps),
                step=500,
            )
        )

    if st.session_state.show_bulk:
        current_zone = st.session_state.current_zone
        target_zone = st.session_state.target_zone
        current_far = FAR_LOOKUP.get(current_zone, 0.5)
        target_far = FAR_LOOKUP.get(target_zone, 1.0)

        current_bulk_lens = land_size * current_far
        target_bulk_lens = land_size * target_far
        target_sellable_lens = target_bulk_lens * 0.85

        st.markdown(
            card_html(
                "🏗️ Bulk Efficiency",
                f"You can build ~<b>{target_bulk_lens:,.0f}m²</b> gross bulk on this <b>{land_size:,}m²</b> plot "
                f"if rezoned from <b>{current_zone}</b> to <b>{target_zone}</b>.<br>"
                f"Approx. sellable area @ 85% efficiency: <b>{target_sellable_lens:,.0f}m²</b>.<br>"
                f"(Current notional bulk: <b>{current_bulk_lens:,.0f}m²</b>.)"
            ),
            unsafe_allow_html=True,
        )
        z1, z2 = st.columns(2)
        with z1:
            st.session_state.current_zone = st.selectbox(
                "Current zone (lens only)",
                list(FAR_LOOKUP.keys()),
                index=list(FAR_LOOKUP.keys()).index(current_zone),
            )
        with z2:
            st.session_state.target_zone = st.selectbox(
                "Target zone (lens only)",
                list(FAR_LOOKUP.keys()),
                index=list(FAR_LOOKUP.keys()).index(target_zone),
            )

    if st.session_state.show_wind:
        wind_text = (
            f"High-wind zone: Adding <b>{wind_glazing_uplift}%</b> to construction cost."
            if wind_on else
            "Wind premium is currently <b>OFF</b>. Toggle it in the sidebar to apply the cost uplift."
        )
        st.markdown(card_html("💨 Coastal Premium", wind_text), unsafe_allow_html=True)

st.divider()


# -----------------------
# Scenario Comparison
# -----------------------
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
# Sensitivity (heritage + wind aware heatmap)
# -----------------------
st.subheader("Sensitivity: IH Requirement vs Density Bonus")

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
            wind_on=wind_on,
            wind_glazing_uplift=wind_glazing_uplift,
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
    xaxis_title="Density Bonus (requested; may be constrained by overlays)",
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
