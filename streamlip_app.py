import streamlit as st
import csv
import re
from io import StringIO
from collections import defaultdict

# --- Mapping tables ---
CATEGORY_MAP = {
    'Office - Open Plan': 1,
    'Office - Enclosed': 2,
    'Storage <50 sq.ft.': 3,
    'Corridor/Transition <8 ft wide': 4,
    'Corridor/Transition >=8 ft wide': 5,
    'Restrooms': 6,
    'Dining Area - Cafeteria/Fast Food': 7,
    'General Seating Area': 8,
    'Lobby For Elevator': 9,
    'Food Preparation': 10,
    'Classroom/Lecture/Training': 11,
    'Conference/Meeting/Multipurpose': 12,
    'Stairwell': 13,
    'Locker Room': 14,
    'Exercise Area (Gymnasium/Fitness Center)': 15,
    'Copy/Print Room': 16,
    'Storage': 17,
    'Dining Area - General': 18,
    'Electrical/Mechanical': 19
}

POWER_DENSITY = {
    1: 16, 2: 18, 3: 9, 4: 13, 5: 14, 6: 19, 7: 14, 8: 10,
    9: 15, 10: 27, 11: 22, 12: 29, 13: 16, 14: 15, 15: 17,
    16: 18, 17: 15, 18: 20, 19: 15
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

def guess_type(name: str) -> str:
    """Heuristic mapping from Room ID to space type."""
    n = name.upper()
    if 'OPEN DESK' in n:
        return 'Office - Open Plan'
    if n.startswith('LARGE OFFICE') or n.startswith('OFFICE'):
        return 'Office - Enclosed'
    if '<50' in n:
        return 'Storage <50 sq.ft.'
    if n.startswith(('MEN', 'WOMEN')) or 'RR ' in n:
        return 'Restrooms'
    if 'CORRIDORS' in n:
        return 'Corridor/Transition >=8 ft wide'
    if any(k in n for k in ('PHONE', 'FLEX ROOM', 'MED MEETING')):
        return 'Conference/Meeting/Multipurpose'
    if any(k in n for k in ('PANTRY', 'PREP PANTRY')):
        return 'Food Preparation'
    if 'ELEVATOR LOBBY' in n:
        return 'Lobby For Elevator'
    return 'Conference/Meeting/Multipurpose'

def parse_wattage(raw: str) -> float:
    """Extract numeric wattage from a string, stripping 'W' or any non-digit."""
    cleaned = re.sub(r'[^\d.]', '', raw)
    return float(cleaned) if cleaned else 0.0

def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # Parse spaces.csv
    reader_s = csv.DictReader(StringIO(spaces_csv), skipinitialspace=True)
    sf_keys = [k for k in reader_s.fieldnames if k.replace(" ", "").lower() == "squarefootage"]
    if not sf_keys:
        raise ValueError(f"spaces.csv must have a 'SquareFootage' column; found {reader_s.fieldnames}")
    sf_key = sf_keys[0]
    spaces = {row['Room ID']: float(row[sf_key]) for row in reader_s}

    # Parse fixtures.csv
    reader_f = csv.DictReader(StringIO(fixtures_csv), skipinitialspace=True)
    fixtures = defaultdict(lambda: defaultdict(int))
    watt_map = {}
    for row in reader_f:
        room = row['Room ID']
        fix  = row['Fixture Description']
        qty  = int(float(row['Quantity']))
        w    = parse_wattage(row['Wattage'])
        fixtures[room][fix] += qty
        watt_map[fix] = w

    # Build static header
    lines = [
        "WARNING: Do Not Modify This File!",
        "Check 24.1.6 Data File",
        "CONTROL 1 (",
        "  code = CEZ_NYSTRETCH_NYC_IECC2018",
        "  compliance mode = UA",
        "  version = 24.1.6 )",
        "LOCATION 1 (",
        "  state = New York",
        "  city = New York )",
        "BUILDING 1 (",
        "  project type = NEW_CONSTRUCTION",
        "  bldg use type = ACTIVITY",
        "  feet bldg height = 0.000",
        "  number of stories = 1",
        "  is nonresidential conditioning = TRUE",
        "  is residential conditioning = FALSE",
        "  is semiheated conditioning = FALSE",
        "  conditioning = HEATING_AND_COOLING)",
        "ENVELOPE 1 (",
        "  use orient details = TRUE",
        "  use vlt details = FALSE",
        "  use cool roof performance details = FALSE",
        "  air barrier compliance type = AIR_BARRIER_OPTION_UNKNOWN",
        "  apply window pct allowance for daylighting = FALSE",
        "  apply skylight pct allowance for daylighting = FALSE )",
        "LIGHTING 1 (",
        "  exterior lighting zone = 0 ",
        "  exterior lighting zone type = EXT_ZONE_UNSPECIFIED )"
    ]

    # INTERIOR SPACE blocks
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP[ctype]
        allowed = POWER_DENSITY[cat]
        total_w = sum(q * watt_map[f] for f, q in fixtures.get(room, {}).items())
        lines += [
            f"INTERIOR SPACE {idx} (",
            f"  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>",
            "  space type = SPACE_INTERIOR_LIGHTING",
            f"  space allowed wattage = {allowed}",
            f"  space prop wattage = {int(total_w)}",
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

    # FIXTURE blocks (aggregated)
    fid = len(spaces) + 1
    for idx, room in enumerate(spaces, start=1):
        for fix, qty in fixtures.get(room, {}).items():
            w = int(watt_map.get(fix, 0))
            lines += [
                f"FIXTURE {fid} (",
                f"  list position = {idx}",
                "  fixture use type = FIXTURE_USE_INTERIOR",
                "  power adjustment factor = 0.000",
                "  paf desc = None",
                "  lamp wattage = 0.00",
                "  lighting type = LED",
                "  type of fixture = <||>",
                f"  description = <|{fix}|>",
                f"  fixture type = <|{fix}|>",
                f"  parent number = {idx}",
                "  lamp ballast description = <||>",
                "  lamp type = Other",
                "  ballast = UNSPECIFIED_BALLAST",
                "  number of lamps = 1",
                f"  fixture wattage = {w}",
                f"  quantity = {qty}",
                ")"
            ]
            fid += 1

    # ACTIVITY USE blocks
    for idx, room in enumerate(spaces, start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP[ctype]
        dtype = ACTIVITY_TYPE[ctype]
        pd = POWER_DENSITY[cat]
        sqft = spaces[room]
        lines += [
            f"ACTIVITY USE {idx} (",
            f"  key = {1000000000 + idx}",
            f"  activity type = {dtype}",
            f"  activity description = <|Common Space Types:{ctype}|>",
            f"  area description = <|{room}|>",
            f"  power density = {pd}",
            "  ceiling height = 0",
            "  internal load = 1.95",
            f"  list position = {idx}",
            "  area factor = 1",
            "  construction type = NON_RESIDENTIAL",
            f"  floor area = {sqft}",
            ")"
        ]

    # Static PROJECT, WHOLE BLDG USE, EXTERIOR USE sections
    lines += [
        "PROJECT 1 (",
        "  project complete = FALSE",
        ")",
        "WHOLE BLDG USE 2 (",
        "  whole bldg type = WHOLE_BUILDING_INVALID_USE",
        "  key = 587260110",
        "  whole bldg description = <||>",
        "  area description = <||>",
        "  power density = 0",
        "  internal load = 0",
        "  ceiling height = 0",
        "  list position = 1",
        "  construction type = NON_RESIDENTIAL",
        "  floor area = 0",
        ")",
        "EXTERIOR USE 1 (",
        "  key = 1417866914",
        "  exterior type = EXTERIOR_INVALID_USE",
        "  exterior description = <||>",
        "  area description = <||>",
        "  power density = 0",
        "  use quantity = 0",
        "  quantity units = <||>",
        "  is tradable = FALSE",
        ")"
    ]

    # REQUIREMENT ANSWER blocks
    for n in range(1, 21):
        lines += [
            f"REQUIREMENT ANSWER {n} (",
            "  requirement = <|PR4_IECC2018_C_C103.2|>" if n == 1 else "  requirement = <|EL26_IECC2018_C_C405.6|>",
            "  category = INTERIOR LIGHTING" if n <= 13 else "  category = PROJECT",
            "  exception name = <||>",
            "  location on plans = <||>",
            "  status = NOT_SATISFIED",
            ")"
        ]

    return "\n".join(lines)

# --- Streamlit UI ---
st.set_page_config(page_title="TDA COMcheck Generator")
logo_url = (
    "https://images.squarespace-cdn.com/"
    "content/v1/651344c15e9ed913545fbbf6/"
    "46e7dba5-6680-4ab9-9745-a0dc87f26000/"
    "TDA+LOGO%2C+JPEG.jpg?format=1500w"
)
st.image(logo_url, width=300)
st.title("TDA COMcheck Generator")

# Sample CSV templates
SAMPLE_FIXTURES = """Room ID,Fixture Description,Quantity,Wattage
OPEN DESK AREA - 17A01,TB-4,2,6 W
"""
SAMPLE_SPACES = """Room ID,SquareFootage
OPEN DESK AREA - 17A01,20
"""

st.markdown("#### Download sample CSV templates to get started. This only works with NYC ECC 2020 at this time.")
c1, c2 = st.columns(2)
with c1:
    st.download_button(
        "Sample fixtures.csv",
        data=SAMPLE_FIXTURES,
        file_name="fixtures_template.csv",
        mime="text/csv"
    )
with c2:
    st.download_button(
        "Sample spaces.csv",
        data=SAMPLE_SPACES,
        file_name="spaces_template.csv",
        mime="text/csv"
    )

# User inputs
output_filename = st.text_input("Output filename:", "TDA_Generated ComCheck File.cck")
f_uploaded = st.file_uploader("Upload fixtures.csv", type="csv")
s_uploaded = st.file_uploader("Upload spaces.csv", type="csv")

# Generate and download
if f_uploaded and s_uploaded:
    try:
        comcheck_text = generate_comcheck(
            f_uploaded.getvalue().decode("utf-8-sig"),
            s_uploaded.getvalue().decode("utf-8-sig")
        )
        st.download_button(
            "Download COMcheck file",
            data=comcheck_text,
            file_name=output_filename,
            mime="text/plain"
        )
    except Exception as e:
        st.error(f"Error generating COMcheck: {e}")
