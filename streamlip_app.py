import io
import re
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
def E(tag, text=None, parent=None):
    el = Element(f"{{{NS}}}{tag}") if parent is None else SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        el.text = str(text)
    return el

def prettify(elem) -> bytes:
    return minidom.parseString(tostring(elem)).toprettyxml(encoding="UTF-8")

def normalize_columns(df: pd.DataFrame, alias_map: dict):
    cols = {c.lower().strip(): c for c in df.columns}
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

def parse_watts(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    s = re.sub(r"[^\d.]+", "", s)  # remove " W", etc.
    try:
        return int(float(s))
    except Exception:
        return s

def load_spaces_df(upload) -> pd.DataFrame:
    raw = pd.read_csv(upload)
    mapping = normalize_columns(raw, SPACE_ALIASES)

    # Use 1st two columns by position if no aliases match (keeps your "Room ID" + "SquareFootage" working)
    desc_series = raw[mapping.get("description", raw.columns[0])]
    area_series = raw[mapping.get("floorArea", raw.columns[1])]
    out = pd.DataFrame({
        "description": desc_series.astype(str),
        "floorArea": pd.to_numeric(area_series, errors="coerce"),
    })

    # activity/lpd: take provided or infer
    if "activityType" in mapping:
        out["activityType"] = raw[mapping["activityType"]].astype(str)
        if "lpd" in mapping:
            out["lpd"] = pd.to_numeric(raw[mapping["lpd"]], errors="coerce")
        else:
            out["lpd"] = out["description"].apply(lambda x: classify_activity(x)[1])
    else:
        acts = out["description"].apply(classify_activity)
        out["activityType"] = acts.apply(lambda x: x[0])
        out["lpd"] = acts.apply(lambda x: x[1])

    # allowances: take provided or default
    out["allowanceType"] = "ALLOWANCE_NONE"
    if "allowanceType" in mapping:
        out["allowanceType"] = raw[mapping["allowanceType"]].fillna("ALLOWANCE_NONE").astype(str)
    out["allowanceFloorArea"] = 0
    if "allowanceFloorArea" in mapping:
        out["allowanceFloorArea"] = pd.to_numeric(raw[mapping["allowanceFloorArea"]], errors="coerce").fillna(0).astype(int)

    return out

def load_fixtures_df(upload) -> pd.DataFrame:
    raw = pd.read_csv(upload)
    mapping = normalize_columns(raw, FIXTURE_ALIASES)

    # Fallback to first 4 columns in typical order if mapping misses
    sd = raw[mapping.get("spaceDescription", raw.columns[0])]
    desc = raw[mapping.get("description", raw.columns[1])]
    qty = raw[mapping.get("quantity", raw.columns[2])]
    watts = raw[mapping.get("fixtureWattage", raw.columns[3])]

    out = pd.DataFrame({
        "spaceDescription": sd.astype(str),
        "description": desc.astype(str),
        "lightingType": "GENERAL_LIGHTING",
        "fixtureType": desc.astype(str),  # can be overridden if you pass a code column
        "lampType": "LED",
        "fixtureWattage": [parse_watts(v) for v in watts],
        "quantity": [int(float(x)) if pd.notna(x) else "" for x in qty],
    })
    # allow explicit overrides if present
    if "lightingType" in mapping: out["lightingType"] = raw[mapping["lightingType"]].astype(str)
    if "fixtureType" in mapping:  out["fixtureType"]  = raw[mapping["fixtureType"]].astype(str)
    if "lampType" in mapping:     out["lampType"]     = raw[mapping["lampType"]].astype(str)
    return out

def validate_spaces_df(df: pd.DataFrame) -> list:
    errs = []
    if df.empty:
        errs.append("Spaces CSV appears empty.")
        return errs
    # Allowance area must not exceed floor area
    bad = df[pd.to_numeric(df["allowanceFloorArea"], errors="coerce") >
             pd.to_numeric(df["floorArea"], errors="coerce")]
    if not bad.empty:
        errs.append("Some rows have allowanceFloorArea > floorArea.")
    # Basic sanity on LPD
    if (df["lpd"] <= 0).any():
        errs.append("Some rows have non-positive LPD. Check activity type mapping.")
    return errs

def validate_fixtures_df(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    errs = []
    if (pd.to_numeric(df["fixtureWattage"], errors="coerce") <= 0).any():
        errs.append("One or more fixtures have non-positive wattage.")
    if (pd.to_numeric(df["quantity"], errors="coerce") <= 0).any():
        errs.append("One or more fixtures have non-positive quantity.")
    return errs

def build_cxl(state:str,
              city:str,
              selected_code_label:str,
              project_name:str,
              owner_name:str,
              notes:str,
              spaces_df: pd.DataFrame,
              fixtures_df: pd.DataFrame,
              version_str: str = DEFAULT_SOFTWARE_VERSION) -> bytes:
    """Build a COMcheck .cxl file (space-by-space + allowances + LPDs)."""

    # Root & boilerplate
    root = E("building")
    root.set("xmlns", NS)
    root.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema-instance")
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

    # Location / Project
    loc = E("location", parent=root);  E("state", state, loc); E("city", city, loc)
    proj = E("project", parent=root)
    E("projectName", project_name, proj)
    E("ownerName", owner_name, proj)
    E("notes", notes, proj)

    # Minimal envelope
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

    # Lighting container + space-by-space structure
    lighting = E("lighting", parent=root)
    E("exteriorLightingZone","0", lighting)
    E("exteriorLightingZoneType","EXT_ZONE_UNSPECIFIED", lighting)

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

    # Fixtures by space (fast lookup)
    fixtures_by_space = {}
    if not fixtures_df.empty:
        for _, row in fixtures_df.iterrows():
            key = str(row["spaceDescription"]).strip()
            fixtures_by_space.setdefault(key, []).append(row)

    # Write spaces + allowances + (optional) fixtures
    for _, sp in spaces_df.iterrows():
        ils = E("interiorLightingSpace", parent=w)
        desc = str(sp["description"]).strip()
        E("description", desc, ils)
        E("allowanceType", str(sp["allowanceType"]).strip(), ils)
        E("allowanceFloorArea", str(int(float(sp["allowanceFloorArea"])) if pd.notna(sp["allowanceFloorArea"]) else 0), ils)
        E("floorArea", str(int(float(sp["floorArea"])) if pd.notna(sp["floorArea"]) else 0), ils)

        for fx in fixtures_by_space.get(desc, []):
            lf = E("lightingFixture", parent=ils)
            for tag in ["description","lightingType","fixtureType","lampType","fixtureWattage","quantity"]:
                val = fx[tag]
                E(tag, str(val).strip(), lf)

    # LPD table (activityUses)
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

# =========================
# Sidebar: project settings
# =========================
with st.sidebar:
    st.header("Project Settings")
    colA, colB = st.columns(2)
    code_label = st.selectbox("COMcheck Code", COMCHECK_CODES, index=COMCHECK_CODES.index("NYC Energy Conservation Code (NYCECC)") if "NYC Energy Conservation Code (NYCECC)" in COMCHECK_CODES else 0)
    version_str = st.text_input("COMcheck Software Version", value=DEFAULT_SOFTWARE_VERSION)
    state = colA.text_input("State", value="New York")
    city = colB.text_input("City", value="New York")
    project_name = st.text_input("Project Name", value="Sample Project")
    owner_name = st.text_input("Owner / Client", value="")
    notes = st.text_area("Notes", value="Generated via Streamlit")

# =========================
# Section 1: CSV templates
# =========================
with st.expander("1) Download CSV templates (optional)"):
    # Spaces template
    spaces_template = pd.DataFrame([
        {"description":"OPEN OFFICE – L38","floorArea":1000,"activityType":"ACTIVITY_COMMON_OFFICE_OPEN_PLAN","lpd":0.86,"allowanceType":"ALLOWANCE_NONE","allowanceFloorArea":0},
        {"description":"LOBBY – L38","floorArea":570,"activityType":"ACTIVITY_COMMON_LOBBY","lpd":0.90,"allowanceType":"ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES","allowanceFloorArea":570},
        {"description":"CONFERENCE – L38","floorArea":709,"activityType":"ACTIVITY_COMMON_CONFERENCE_HALL","lpd":0.93,"allowanceType":"ALLOWANCE_DECORATIVE_APPEARANCE_OTHER","allowanceFloorArea":200},
    ])
    fixtures_template = pd.DataFrame([
        {"spaceDescription":"OPEN OFFICE – L38","description":"2x4 Recessed LED Troffer","lightingType":"GENERAL_LIGHTING","fixtureType":"L1","lampType":"LED","fixtureWattage":28,"quantity":20},
        {"spaceDescription":"LOBBY – L38","description":"Downlight","lightingType":"GENERAL_LIGHTING","fixtureType":"DL1","lampType":"LED","fixtureWattage":12,"quantity":40},
        {"spaceDescription":"CONFERENCE – L38","description":"Linear Pendant","lightingType":"GENERAL_LIGHTING","fixtureType":"P1","lampType":"LED","fixtureWattage":35,"quantity":10},
    ])
    st.download_button(
        "Download spaces_template.csv",
        data=spaces_template.to_csv(index=False).encode("utf-8"),
        file_name="spaces_template.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download fixtures_template.csv",
        data=fixtures_template.to_csv(index=False).encode("utf-8"),
        file_name="fixtures_template.csv",
        mime="text/csv",
    )
    st.write("Tip: You can also import your **Room ID / SquareFootage** files directly—this app auto-maps them.")

# =========================
# Section 2: Upload CSVs
# =========================
with st.expander("2) Upload your CSVs (spaces & fixtures)"):
    left, right = st.columns(2)
    spaces_file = left.file_uploader("Upload Spaces CSV", type=["csv"], accept_multiple_files=False)
    fixtures_file = right.file_uploader("Upload Fixtures CSV (optional)", type=["csv"], accept_multiple_files=False)

    spaces_df = pd.DataFrame()
    fixtures_df = pd.DataFrame()

    if spaces_file:
        try:
            spaces_df = load_spaces_df(spaces_file)
            st.success("Spaces loaded and normalized.")
            st.dataframe(spaces_df.head(20), use_container_width=True)
        except Exception as e:
            st.error(f"Failed to read spaces CSV: {e}")

    if fixtures_file:
        try:
            fixtures_df = load_fixtures_df(fixtures_file)
            st.success("Fixtures loaded and normalized.")
            st.dataframe(fixtures_df.head(20), use_container_width=True)
        except Exception as e:
            st.error(f"Failed to read fixtures CSV: {e}")

# =========================
# Section 3: Inline editor
# =========================
with st.expander("3) Review & edit (activity types, LPDs, allowances)"):
    if not spaces_df.empty:
        # Constrain allowanceType to known options, but allow arbitrary edits via text if desired
        editable = spaces_df.copy()
        # Show a friendlier selector for allowanceType
        editable["allowanceType"] = editable["allowanceType"].apply(lambda v: v if v in ALLOWANCE_TYPES else "ALLOWANCE_NONE")

        edited = st.data_editor(
            editable,
            use_container_width=True,
            column_config={
                "activityType": st.column_config.TextColumn(help="COMcheck activity code (e.g., ACTIVITY_COMMON_OFFICE_OPEN_PLAN)"),
                "lpd": st.column_config.NumberColumn(format="%.2f", help="Allowed watts/sf baseline for this activity"),
                "allowanceType": st.column_config.SelectboxColumn(options=ALLOWANCE_TYPES, help="Set decorative allowances if applicable"),
                "allowanceFloorArea": st.column_config.NumberColumn(format="%d", help="Area (sf) claimed for the allowance"),
                "floorArea": st.column_config.NumberColumn(format="%d", help="Space floor area (sf)"),
            },
            num_rows="dynamic",
        )
        spaces_df = edited

        # Quick validation feedback
        v_errs = validate_spaces_df(spaces_df)
        if v_errs:
            for e in v_errs:
                st.warning(e)

# =========================
# Section 4: Generate CXL
# =========================
with st.expander("4) Generate .cxl", expanded=True):
    disabled = spaces_df.empty or bool(validate_spaces_df(spaces_df))
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
        st.success("CXL ready! Import it in COMcheck-Web: Project → Import.")
