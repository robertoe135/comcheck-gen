import io
import pandas as pd
import streamlit as st
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# -----------------------
# Constants & dictionaries
# -----------------------
NS = "http://energycode.pnl.gov/ns/ComCheckBuildingSchema"

# Codes supported by COMcheck-Web (per EnergyCodes.gov, July 1, 2025)
# Ref: https://www.energycodes.gov (COMcheck supported codes page)
COMCHECK_CODES = [
    # National model codes
    "IECC 2015",
    "IECC 2018",
    "IECC 2021",
    "IECC 2024",
    "ASHRAE 90.1-2013",
    "ASHRAE 90.1-2016",
    "ASHRAE 90.1-2019",
    "ASHRAE 90.1-2022",
    # State/City variants implemented in COMcheck
    "Boulder, CO",
    "Denver, CO",
    "Massachusetts Commercial Energy Code",
    "Minnesota Commercial Energy Code",
    "NYC Energy Conservation Code (NYCECC)",
    "NYStretch-2020",
    "Vermont 2020",
    "Ontario 2017",
    "Puerto Rico 2011",
]

# Map UI labels to ComCheck "control/code" strings used in .cxl
CODE_TO_CONTROL = {
    "IECC 2015": "CEZ_IECC2015",
    "IECC 2018": "CEZ_IECC2018",
    "IECC 2021": "CEZ_IECC2021",
    "IECC 2024": "CEZ_IECC2024",
    "ASHRAE 90.1-2013": "CEZ_ASHRAE90_1_2013",
    "ASHRAE 90.1-2016": "CEZ_ASHRAE90_1_2016",
    "ASHRAE 90.1-2019": "CEZ_ASHRAE90_1_2019",
    "ASHRAE 90.1-2022": "CEZ_ASHRAE90_1_2022",
    "Boulder, CO": "CEZ_LOCAL_BOULDER",
    "Denver, CO": "CEZ_LOCAL_DENVER",
    "Massachusetts Commercial Energy Code": "CEZ_LOCAL_MASSACHUSETTS",
    "Minnesota Commercial Energy Code": "CEZ_LOCAL_MINNESOTA",
    "NYC Energy Conservation Code (NYCECC)": "CEZ_LOCAL_NYCECC",
    "NYStretch-2020": "CEZ_LOCAL_NYSTRETCH_2020",
    "Vermont 2020": "CEZ_LOCAL_VERMONT_2020",
    "Ontario 2017": "CEZ_LOCAL_ONTARIO_2017",
    "Puerto Rico 2011": "CEZ_LOCAL_PUERTO_RICO_2011",
}

# ComCheck wants “UA” or “PERFORMANCE” complianceMode; we’ll use UA for lighting/space-by-space
DEFAULT_COMPLIANCE_MODE = "UA"

# -----------------------
# Helper functions
# -----------------------
def E(tag, text=None, parent=None):
    """Create a namespaced element"""
    el = Element(f"{{{NS}}}{tag}") if parent is None else SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = str(text)
    return el

def prettify(elem) -> bytes:
    """Return pretty-printed XML as bytes (UTF-8)."""
    return minidom.parseString(tostring(elem)).toprettyxml(encoding="UTF-8")

def validate_spaces_df(df: pd.DataFrame) -> list:
    """Basic validations and user-friendly errors."""
    required_cols = ["description","floorArea","activityType","lpd","allowanceType","allowanceFloorArea"]
    missing = [c for c in required_cols if c not in df.columns]
    errs = []
    if missing:
        errs.append(f"Spaces CSV missing required columns: {', '.join(missing)}")

    if "floorArea" in df.columns and "allowanceFloorArea" in df.columns:
        bad = df[(pd.to_numeric(df["allowanceFloorArea"], errors="coerce") >
                  pd.to_numeric(df["floorArea"], errors="coerce"))]
        if not bad.empty:
            errs.append("Some rows have allowanceFloorArea > floorArea. Please correct those before export.")

    return errs

def validate_fixtures_df(df: pd.DataFrame) -> list:
    """Check fixture CSV integrity."""
    if df.empty:
        return []
    required_cols = ["spaceDescription","description","lightingType","fixtureType","lampType","fixtureWattage","quantity"]
    missing = [c for c in required_cols if c not in df.columns]
    errs = []
    if missing:
        errs.append(f"Fixtures CSV missing required columns: {', '.join(missing)}")
    return errs

def build_cxl(state:str,
              city:str,
              selected_code_label:str,
              project_name:str,
              owner_name:str,
              notes:str,
              spaces_df: pd.DataFrame,
              fixtures_df: pd.DataFrame,
              version_str: str = "24.1.6") -> bytes:
    """
    Build a COMcheck .cxl file from inputs (spaces + fixtures).
    The structure tracks the schema used by COMcheck-Web.
    """

    # Root
    root = E("building")
    root.set("xmlns", NS)
    root.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema-instance")

    # Required boilerplate
    for k, v in [
        ("projectType","NEW_CONSTRUCTION"),
        ("bldgUseType","ACTIVITY"),
        ("feetBldgHeight","0.000"),
        ("isNonresidentialConditioning","true"),
        ("isResidentialConditioning","false"),
        ("isSemiheatedConditioning","false"),
        ("conditioning","HEATING_AND_COOLING"),
    ]:
        E(k, v, root)

    # Control (code/version/mode)
    ctrl = E("control", parent=root)
    E("code", CODE_TO_CONTROL.get(selected_code_label, "CEZ_IECC2018"), ctrl)
    E("complianceMode", DEFAULT_COMPLIANCE_MODE, ctrl)
    E("version", version_str, ctrl)

    # Location
    loc = E("location", parent=root)
    E("state", state, loc)
    E("city", city, loc)

    # Project
    proj = E("project", parent=root)
    E("projectName", project_name, proj)
    E("ownerName", owner_name, proj)
    E("notes", notes, proj)

    # Envelope (minimal, required by schema)
    env = E("envelope", parent=root)
    for k, v in [
        ("useOrientDetails","true"),
        ("useVltDetails","false"),
        ("useCoolRoofPerformanceDetails","false"),
        ("airBarrierComplianceType","AIR_BARRIER_OPTION_UNKNOWN"),
        ("applyWindowPctAllowanceForDaylighting","false"),
        ("applySkylightPctAllowanceForDaylighting","false"),
    ]:
        E(k, v, env)

    # Lighting container
    lighting = E("lighting", parent=root)
    E("exteriorLightingZone","0", lighting)
    E("exteriorLightingZoneType","EXT_ZONE_UNSPECIFIED", lighting)

    # Space-by-space structure
    wb = E("wholeBldgUses", parent=lighting)
    w = E("wholeBldgUse", parent=wb)
    for k, v in [
        ("wholeBldgType","WHOLE_BUILDING_INVALID_USE"),
        ("key","1"),
        ("powerDensity","0"),
        ("internalLoad","0"),
        ("ceilingHeight","0"),
        ("listPosition","1"),
        ("constructionType","NON_RESIDENTIAL"),
        ("floorArea","0"),
    ]:
        E(k, v, w)

    # Build a map of fixtures keyed by spaceDescription
    fixtures_by_space = {}
    if not fixtures_df.empty:
        for _, row in fixtures_df.iterrows():
            key = str(row["spaceDescription"]).strip()
            fixtures_by_space.setdefault(key, []).append(row)

    # Write each interiorLightingSpace and attach fixtures
    for _, sp in spaces_df.iterrows():
        ils = E("interiorLightingSpace", parent=w)
        desc = str(sp["description"]).strip()
        E("description", desc, ils)
        E("allowanceType", str(sp["allowanceType"]).strip(), ils)
        E("allowanceFloorArea", str(sp["allowanceFloorArea"]).strip(), ils)
        E("floorArea", str(sp["floorArea"]).strip(), ils)

        # optional fixtures
        for fx in fixtures_by_space.get(desc, []):
            lf = E("lightingFixture", parent=ils)
            for tag in ["description","lightingType","fixtureType","lampType","fixtureWattage","quantity"]:
                val = fx[tag]
                E(tag, str(val).strip(), lf)

    # LPD table (activityUses) — one row per space
    aus = E("activityUses", parent=lighting)
    for _, sp in spaces_df.iterrows():
        au = E("activityUse", parent=aus)
        desc = str(sp["description"]).strip()
        E("key", desc, au)
        E("activityType", str(sp["activityType"]).strip(), au)
        E("activityDescription", desc, au)
        E("areaDescription", desc, au)
        E("powerDensity", str(sp["lpd"]).strip(), au)

    # Requirements (minimal)
    req = E("requirements", parent=root)
    E("energyCode", CODE_TO_CONTROL.get(selected_code_label, "CEZ_IECC2018"), req)
    E("softwareVersion", version_str, req)

    return prettify(root)

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="COMcheck CXL Generator", page_icon="💡", layout="centered")
st.title("COMcheck CXL Generator 💡")
st.caption("Build a space-by-space COMcheck **.cxl** (with allowances + LPDs) from CSVs.")

with st.expander("1) Select code & project details", expanded=True):
    colA, colB = st.columns(2)
    code_label = colA.selectbox("COMcheck code / jurisdiction", COMCHECK_CODES, index=COMCHECK_CODES.index("NYC Energy Conservation Code (NYCECC)") if "NYC Energy Conservation Code (NYCECC)" in COMCHECK_CODES else 0)
    version_str = colB.text_input("Target COMcheck software version", value="24.1.6", help="Leave as-is unless you need to match a specific exported file.")

    state = colA.text_input("State", value="New York")
    city = colB.text_input("City", value="New York")
    project_name = st.text_input("Project name", value="Sample Project")
    owner_name = st.text_input("Owner / Client", value="")
    notes = st.text_area("Notes", value="Generated via Streamlit")

with st.expander("2) Upload CSVs (Spaces & Fixtures)", expanded=True):
    st.markdown("**Spaces CSV columns (required):** `description, floorArea, activityType, lpd, allowanceType, allowanceFloorArea`")
    st.markdown("**Fixtures CSV columns (optional):** `spaceDescription, description, lightingType, fixtureType, lampType, fixtureWattage, quantity`")
    st.markdown(
        "- Download samples: "
        "[spaces_sample.csv](sandbox:/mnt/data/spaces_sample.csv) · "
        "[fixtures_sample.csv](sandbox:/mnt/data/fixtures_sample.csv)"
    )

    spaces_file = st.file_uploader("Upload Spaces CSV", type=["csv"], accept_multiple_files=False)
    fixtures_file = st.file_uploader("Upload Fixtures CSV (optional)", type=["csv"], accept_multiple_files=False)

    spaces_df = pd.DataFrame()
    fixtures_df = pd.DataFrame()

    if spaces_file:
        spaces_df = pd.read_csv(spaces_file)
        st.write("Spaces preview:", spaces_df.head(10))
        errs = validate_spaces_df(spaces_df)
        if errs:
            st.error(" • ".join(errs))

    if fixtures_file:
        fixtures_df = pd.read_csv(fixtures_file)
        st.write("Fixtures preview:", fixtures_df.head(10))
        ferrs = validate_fixtures_df(fixtures_df)
        if ferrs:
            st.error(" • ".join(ferrs))

with st.expander("3) Generate .cxl", expanded=True):
    disabled = spaces_df.empty or (len(validate_spaces_df(spaces_df)) > 0)
    if st.button("Generate .cxl", disabled=disabled):
        xml_bytes = build_cxl(
            state=state,
            city=city,
            selected_code_label=code_label,
            project_name=project_name,
            owner_name=owner_name,
            notes=notes,
            spaces_df=spaces_df,
            fixtures_df=fixtures_df,
            version_str=version_str,
        )
        st.download_button(
            label="Download CXL",
            data=xml_bytes,
            file_name=f"{project_name.replace(' ','_')}.cxl",
            mime="application/xml",
        )
        st.success("CXL ready! Import this file into COMcheck-Web via Project → Import.")
