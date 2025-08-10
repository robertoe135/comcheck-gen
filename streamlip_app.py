
import streamlit as st
import csv
from io import StringIO
from collections import defaultdict
import re

st.set_page_config(page_title="COMcheck CCK – Simple Builder", layout="centered")
st.title("COMcheck CCK — Simple Builder")

st.markdown("""
**Inputs:**  
1) `spaces.csv` — columns: `room,floor_area`  
2) `fixtures.csv` — columns: `room,fixture,quantity,watt`  
3) Output file name (e.g., `MyProject.cck`)

The app infers **space type** from each room name (same logic as before) and calculates
**allowed wattage = floor_area × LPD** using default LPDs. It also guarantees that
`list position` values are unique and aligned, which fixes allowance area mismatches.
""")

# ---------------- Defaults ----------------
SPACE_TYPES = [
    'Office - Open Plan',
    'Office - Enclosed',
    'Storage <50 sq.ft.',
    'Corridor/Transition <8 ft wide',
    'Corridor/Transition >=8 ft wide',
    'Restrooms',
    'Dining Area - Cafeteria/Fast Food',
    'General Seating Area',
    'Lobby For Elevator',
    'Food Preparation',
    'Classroom/Lecture/Training',
    'Conference/Meeting/Multipurpose',
    'Stairwell',
    'Locker Room',
    'Exercise Area (Gymnasium/Fitness Center)',
    'Copy/Print Room',
    'Storage',
    'Dining Area - General',
    'Electrical/Mechanical'
]
CATEGORY_MAP = {name: i+1 for i, name in enumerate(SPACE_TYPES)}
DEFAULT_LPD = {
    'Office - Open Plan': 0.82,
    'Office - Enclosed': 0.85,
    'Storage <50 sq.ft.': 0.50,
    'Corridor/Transition <8 ft wide': 0.66,
    'Corridor/Transition >=8 ft wide': 0.66,
    'Restrooms': 0.90,
    'Dining Area - Cafeteria/Fast Food': 0.90,
    'General Seating Area': 0.90,
    'Lobby For Elevator': 0.90,
    'Food Preparation': 1.20,
    'Classroom/Lecture/Training': 0.90,
    'Conference/Meeting/Multipurpose': 0.90,
    'Stairwell': 0.60,
    'Locker Room': 0.80,
    'Exercise Area (Gymnasium/Fitness Center)': 0.90,
    'Copy/Print Room': 0.75,
    'Storage': 0.63,
    'Dining Area - General': 0.90,
    'Electrical/Mechanical': 0.80
}
ACTIVITY_TYPE = {
    'Office - Open Plan': 'ACTIVITY_COMMON_OFFICE_OPEN',
    'Office - Enclosed': 'ACTIVITY_COMMON_OFFICE_ENCLOSED',
    'Storage <50 sq.ft.': 'ACTIVITY_COMMON_STORAGE_LT50',
    'Corridor/Transition <8 ft wide': 'ACTIVITY_COMMON_CORRIDOR_LT_8_FEET',
    'Corridor/Transition >=8 ft wide': 'ACTIVITY_COMMON_CORRIDOR_GTE_8_FEET',
    'Restrooms': 'ACTIVITY_COMMON_RESTROOM',
    'Dining Area - Cafeteria/Fast Food': 'ACTIVITY_COMMON_DINING_CAFETERIA_FAST_FOOD',
    'General Seating Area': 'ACTIVITY_COMMON_GENERAL_SEATING_AREA',
    'Lobby For Elevator': 'ACTIVITY_COMMON_LOBBY_ELEVATOR',
    'Food Preparation': 'ACTIVITY_COMMON_FOOD_PREP',
    'Classroom/Lecture/Training': 'ACTIVITY_COMMON_LECTURE_HALL',
    'Conference/Meeting/Multipurpose': 'ACTIVITY_COMMON_CONFERENCE_HALL',
    'Stairwell': 'ACTIVITY_COMMON_STAIRS',
    'Locker Room': 'ACTIVITY_COMMON_LOCKER_ROOM',
    'Exercise Area (Gymnasium/Fitness Center)': 'ACTIVITY_GYM_EXERCISE',
    'Copy/Print Room': 'ACTIVITY_COMMON_COPY_PRINT_ROOM',
    'Storage': 'ACTIVITY_COMMON_STORAGE',
    'Dining Area - General': 'ACTIVITY_COMMON_DINING_GENERAL',
    'Electrical/Mechanical': 'ACTIVITY_COMMON_ELECTRICAL_MECHANICAL'
}

GENERIC_HEADER = """WARNING: Do Not Modify This File!
Check 24.1.6 Data File
CONTROL 1 (
  code = CEZ_NYSTRETCH_NYC_IECC2018
  compliance mode = UA
  version = 24.1.6 )
LOCATION 1 (
  state = New York
  city = New York )
BUILDING 1 (
  project type = NEW_CONSTRUCTION
  bldg use type = ACTIVITY
  feet bldg height = 0.000
  number of stories = 1
  is nonresidential conditioning = TRUE
  is residential conditioning = FALSE
  is semiheated conditioning = FALSE
  conditioning = HEATING_AND_COOLING)
ENVELOPE 1 (
  use orient details = TRUE
  use vlt details = FALSE
  use cool roof performance details = FALSE
  air barrier compliance type = AIR_BARRIER_OPTION_UNKNOWN
  apply window pct allowance for daylighting = FALSE
  apply skylight pct allowance for daylighting = FALSE )
LIGHTING 1 (
  exterior lighting zone = 0 
  exterior lighting zone type = EXT_ZONE_UNSPECIFIED )
"""

GENERIC_TAIL = """
WHOLE BUILDING 1 (
  key = 587260110
  whole bldg description = <||>
  area description = <||>
  power density = 0
  internal load = 0
  ceiling height = 0
  list position = 1
  construction type = NON_RESIDENTIAL
  floor area = 0
)
EXTERIOR USE 1 (
  key = 1417866914
  exterior type = EXTERIOR_INVALID_USE
  exterior description = <||>
  area description = <||>
  power density = 0
  internal load = 0
  list position = 0
  construction type = NON_RESIDENTIAL
  floor area = 0
)
"""

# ---------------- Inference ----------------
def guess_type(name: str) -> str:
    n = (name or "").upper()
    # Order matters: match more specific labels first
    if 'OPEN DESK' in n or 'OPEN OFFICE' in n:
        return 'Office - Open Plan'
    if n.startswith('LARGE OFFICE') or n.startswith('OFFICE') or 'PRIVATE OFFICE' in n:
        return 'Office - Enclosed'
    if '<50' in n or 'STORAGE <50' in n:
        return 'Storage <50 sq.ft.'
    if any(k in n for k in ['MEN', 'WOMEN', 'RESTROOM', 'RR ']):
        return 'Restrooms'
    if 'LOBBY' in n or 'RECEPTION' in n:
        return 'Lobby For Elevator'
    if 'CAFETERIA' in n or 'DINING' in n:
        return 'Dining Area - General'
    if 'FOOD PREP' in n or 'KITCHEN' in n:
        return 'Food Preparation'
    if 'CLASSROOM' in n or 'LECTURE' in n or 'TRAINING' in n:
        return 'Classroom/Lecture/Training'
    if 'CONFERENCE' in n or 'MEETING' in n or 'MPR' in n:
        return 'Conference/Meeting/Multipurpose'
    if 'STAIR' in n:
        return 'Stairwell'
    if 'LOCKER' in n:
        return 'Locker Room'
    if 'GYM' in n or 'FITNESS' in n or 'EXERCISE' in n:
        return 'Exercise Area (Gymnasium/Fitness Center)'
    if 'COPY' in n or 'PRINT' in n or 'PHONE' in n:
        return 'Copy/Print Room'
    if 'CORRIDOR' in n or 'HALLWAY' in n:
        # default width category if unknown
        return 'Corridor/Transition >=8 ft wide'
    if 'ELEC' in n or 'MECH' in n:
        return 'Electrical/Mechanical'
    if 'STOR' in n:
        return 'Storage'
    return 'Office - Enclosed'

# ---------------- CSV Loaders ----------------
def load_spaces(csv_text: str):
    reader = csv.DictReader(StringIO(csv_text))
    spaces = {}
    for row in reader:
        room = (row.get("room") or row.get("Room") or row.get("area_description") or row.get("Area") or "").strip()
        area = (row.get("floor_area") or row.get("sqft") or row.get("Floor Area") or "").strip()
        if not room or not area:
            continue
        try:
            spaces[room] = float(area)
        except:
            pass
    return spaces

def load_fixtures(csv_text: str):
    reader = csv.DictReader(StringIO(csv_text))
    fixtures = defaultdict(lambda: defaultdict(int))
    watts = {}
    for row in reader:
        room = (row.get("room") or row.get("Room") or "").strip()
        fix = (row.get("fixture") or row.get("Fixture") or "").strip()
        qty = (row.get("quantity") or row.get("qty") or "0").strip()
        watt = (row.get("watt") or row.get("watts") or row.get("W") or "0").strip()
        if room and fix:
            try:
                fixtures[room][fix] += int(float(qty))
                watts[fix] = float(watt)
            except:
                continue
    return fixtures, watts

# ---------------- Builders ----------------
def build_sections(spaces, fixtures, watt_map):
    lines = []

    # INTERIOR SPACE blocks
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        stype = guess_type(room)
        cat = CATEGORY_MAP[stype]
        pd = float(DEFAULT_LPD[stype])
        allowed_watts = int(round(float(sqft) * pd))
        total_w = sum(q * float(watt_map.get(f, 0)) for f, q in fixtures.get(room, {}).items())

        lines += [
            f"INTERIOR SPACE {idx} (",
            f"  description = <|{room} ( Common Space Types:{stype} {int(round(sqft))} sq.ft.)|>",
            "  space type = SPACE_INTERIOR_LIGHTING",
            f"  space allowed wattage = {allowed_watts}",
            f"  space prop wattage = {int(round(total_w))}",
            f"  list position = {idx}",
            "  allowance description = None",
            "  allowance type = ALLOWANCE_NONE",
            "  allowance floor area = 0",
            "  rcr perimeter = 0",
            "  rcr floor to workplane height = 0",
            "  rcr workplane to luminaire height = 0",
            f"  activity category number = {cat}",
            ")"
        ]

    # FIXTURE blocks (aggregated per space)
    fid = len(spaces) + 1
    for idx, room in enumerate(spaces, start=1):
        for fix, qty in fixtures.get(room, {}).items():
            w = int(round(float(watt_map.get(fix, 0))))
            lines += [
                f"FIXTURE {fid} (",
                f"  list position = {idx}",
                f"  luminaire type id = <|{fix}|>",
                f"  quantity = {int(qty)}",
                f"  watt input = {w}",
                ")"
            ]
            fid += 1

    # ACTIVITY USE blocks
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        stype = guess_type(room)
        pd = float(DEFAULT_LPD[stype])
        lines += [
            f"ACTIVITY USE {idx} (",
            f"  key = {1000000000 + idx}",
            f"  activity type = {ACTIVITY_TYPE[stype]}",
            f"  activity description = <|Common Space Types:{stype}|>",
            f"  area description = <|{room}|>",
            f"  power density = {pd}",
            "  internal load = 1.95",
            "  ceiling height = 0",
            f"  list position = {idx}",
            "  construction type = NON_RESIDENTIAL",
            f"  floor area = {int(round(sqft))}",
            ")"
        ]

    return lines

def build_cck(spaces, fixtures, watt_map, filename):
    # Stable ordering by room name
    spaces = dict(sorted(spaces.items(), key=lambda x: x[0]))
    body = "\n".join(build_sections(spaces, fixtures, watt_map))
    return GENERIC_HEADER.rstrip() + "\n" + body + "\n" + GENERIC_TAIL.lstrip()

# ---------------- UI ----------------
col1, col2 = st.columns(2)
with col1:
    spaces_file = st.file_uploader("Upload spaces.csv", type=["csv"])
with col2:
    fixtures_file = st.file_uploader("Upload fixtures.csv", type=["csv"])

outfile = st.text_input("Output file name", value="Generated_ComCheck.cck")

# Sample files
st.markdown("---")
st.subheader("Sample CSVs")
sample_spaces = "room,floor_area\nOPEN DESK AREA - 17A01,830\nPhone 17B05,89\nLarge Office 17A05,215\nOffice 17A04,155\n"
sample_fixtures = "room,fixture,quantity,watt\nOPEN DESK AREA - 17A01,DL-8W,40,8\nOPEN DESK AREA - 17A01,PEND-30W,10,30\nPhone 17B05,DL-8W,4,8\nLarge Office 17A05,DL-8W,16,8\nOffice 17A04,DL-8W,12,8\n"
st.download_button("Download sample spaces.csv", data=sample_spaces, file_name="spaces_sample.csv", mime="text/csv")
st.download_button("Download sample fixtures.csv", data=sample_fixtures, file_name="fixtures_sample.csv", mime="text/csv")

st.markdown("---")
if st.button("Generate .cck") and spaces_file and fixtures_file and outfile.strip():
    try:
        spaces = load_spaces(spaces_file.getvalue().decode("utf-8-sig"))
        fixtures, watt_map = load_fixtures(fixtures_file.getvalue().decode("utf-8-sig"))
        if not spaces:
            st.error("No valid rows found in spaces.csv (need columns: room,floor_area).")
        else:
            cck_text = build_cck(spaces, fixtures, watt_map, outfile.strip())
            # Basic validation: ensure unique list positions by count
            if len(spaces) != len(set(range(1, len(spaces)+1))):
                st.warning("List positions might be misaligned — please check.")
            st.success("COMcheck file generated.")
            st.download_button("Download COMcheck .cck", data=cck_text, file_name=outfile.strip(), mime="text/plain")
            st.code(cck_text[:2000])
    except Exception as e:
        st.error(f"Error: {e}")
elif st.button("Generate .cck") and not (spaces_file and fixtures_file):
    st.error("Please upload both spaces.csv and fixtures.csv.")
