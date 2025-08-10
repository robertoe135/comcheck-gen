import io
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# =========================
# App metadata
# =========================
st.set_page_config(page_title="COMcheck CXL Generator", page_icon="💡", layout="wide")
st.title("COMcheck CXL Generator 💡")
st.caption("Build a space-by-space COMcheck **.cxl** (with allowances + LPDs) from your CSVs.")

# =========================
# Constants & dictionaries
# =========================
NS = "http://energycode.pnl.gov/ns/ComCheckBuildingSchema"
DEFAULT_COMPLIANCE_MODE = "UA"
DEFAULT_SOFTWARE_VERSION = "24.1.6"   # keep as-is unless you must match a specific export

# Codes supported in COMcheck (UI label → control code string in CXL)
COMCHECK_CODES = [
    "IECC 2015",
    "IECC 2018",
    "IECC 2021",
    "IECC 2024",
    "ASHRAE 90.1-2013",
    "ASHRAE 90.1-2016",
    "ASHRAE 90.1-2019",
    "ASHRAE 90.1-2022",
    "NYC Energy Conservation Code (NYCECC)",
    "NYStretch-2020",
    "Boulder, CO",
    "Denver, CO",
    "Massachusetts Commercial Energy Code",
    "Minnesota Commercial Energy Code",
    "Vermont 2020",
    "Ontario 2017",
    "Puerto Rico 2011",
]
CODE_TO_CONTROL = {
    "IECC 2015": "CEZ_IECC2015",
    "IECC 2018": "CEZ_IECC2018",
    "IECC 2021": "CEZ_IECC2021",
    "IECC 2024": "CEZ_IECC2024",
    "ASHRAE 90.1-2013": "CEZ_ASHRAE90_1_2013",
    "ASHRAE 90.1-2016": "CEZ_ASHRAE90_1_2016",
    "ASHRAE 90.1-2019": "CEZ_ASHRAE90_1_2019",
    "ASHRAE 90.1-2022": "CEZ_ASHRAE90_1_2022",
    "NYC Energy Conservation Code (NYCECC)": "CEZ_LOCAL_NYCECC",
    "NYStretch-2020": "CEZ_LOCAL_NYSTRETCH_2020",
    "Boulder, CO": "CEZ_LOCAL_BOULDER",
    "Denver, CO": "CEZ_LOCAL_DENVER",
    "Massachusetts Commercial Energy Code": "CEZ_LOCAL_MASSACHUSETTS",
    "Minnesota Commercial Energy Code": "CEZ_LOCAL_MINNESOTA",
    "Vermont 2020": "CEZ_LOCAL_VERMONT_2020",
    "Ontario 2017": "CEZ_LOCAL_ONTARIO_2017",
    "Puerto Rico 2011": "CEZ_LOCAL_PUERTO_RICO_2011",
}

# Common allowance types seen in projects; extend if needed
ALLOWANCE_TYPES = [
    "ALLOWANCE_NONE",
    "ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES",
    "ALLOWANCE_DECORATIVE_APPEARANCE_OTHER",
]

# CSV alias maps (we’ll auto-detect columns)
SPACE_ALIASES = {
    "description": ["description", "room id", "room", "space", "space name", "name"],
    "floorArea": ["floorarea", "sqft", "squarefootage", "area (sf)", "area_sf", "area"],
    "activityType": ["activitytype", "space type", "space_type", "comcheck activity", "common space type"],
    "lpd": ["lpd", "w/sf", "watts/sf", "w_per_sf"],
    "allowanceType": ["allowancetype", "allowance type"],
    "allowanceFloorArea": ["allowancefloorarea", "allowance area", "allowance_area_sf"],
}
FIXTURE_ALIASES = {
    "spaceDescription": ["spacedescription", "room id", "space", "description", "room"],
    "description": ["description", "fixture", "fixture description", "type"],
    "lightingType": ["lightingtype", "lighting type"],
    "fixtureType": ["fixturetype", "type code", "symbol", "tag"],
    "lampType": ["lamptype", "lamp type"],
    "fixtureWattage": ["fixturewattage", "wattage", "watts", "w"],
    "quantity": ["quantity", "qty", "count"],
}

# =========================
# Helpers
# =========================
def safe_text(x, default=""):
    return str(x) if x is not None else default

def slugify_name(x, fallback_prefix="comcheck_project"):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(x or "").strip())
    if not base:
        base = f"{fallback_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return base

def E(tag, text=None, parent=None):
    el = Element(f"{{{NS}}}{tag}") if parent is None else SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = safe_text(text, "")
    return el

def prettify(elem) -> bytes:
    return minidom.parseString(tostring(elem)).toprettyxml(encoding="UTF-8")

def normalize_columns(df: pd.DataFrame, alias_map: dict):
    cols = {str(c).lower().strip(): c for c in df.columns}
    out = {}
    for target, aliases in alias_map.items():
        for a in aliases:
            if a in cols:
                out[target] = cols[a]
                break
    return out

def classify_activity(desc: str):
    d = (str(desc) if pd.notna(desc) else "").lower()
    if any(k in d for k in ["open desk", "open office", "workstation", "desks"]):
        return "ACTIVITY_COMMON_OFFICE_OPEN_PLAN", 0.86
    if any(k in d for k in ["large office", "private office", "office"]):
        return "ACTIVITY_COMMON_OFFICE_ENCLOSED", 0.79
    if any(k in d for k in ["conference", "phone", "huddle", "meeting"]):
        return "ACTIVITY_COMMON_CONFERENCE_HALL", 0.93
    if any(k in d for k in ["lobby", "reception", "prefunction"]):
        return "ACTIVITY_COMMON_LOBBY", 0.90
    if any(k in d for k in ["corridor", "hall", "hallway"]):
        return "ACTIVITY_COMMON_CORRIDOR", 0.66
    return "ACTIVITY_COMMON_OFFICE_OPEN_PLAN", 0.86  # fallback
