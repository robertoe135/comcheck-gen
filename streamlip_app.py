import streamlit as st
import csv
from io import StringIO
from collections import defaultdict

# --- Mapping tables (copy from our example) ---
CATEGORY_MAP = {
    'Office - Open Plan': 1,
    'Office - Enclosed':   2,
    'Storage <50 sq.ft.':   3,
    'Corridor/Transition <8 ft wide': 4,
    'Corridor/Transition >=8 ft wide': 5,
    'Restrooms':            6,
    'Dining Area - Cafeteria/Fast Food': 7,
    'General Seating Area': 8,
    'Lobby For Elevator':   9,
    'Food Preparation':    10,
    'Classroom/Lecture/Training': 11,
    'Conference/Meeting/Multipurpose': 12,
    'Stairwell':           13,
    'Locker Room':         14,
    'Exercise Area (Gymnasium/Fitness Center)': 15,
    'Copy/Print Room':     16,
    'Storage':             17,
    'Dining Area - General': 18,
    'Electrical/Mechanical': 19
}

POWER_DENSITY = {
    1:16,  2:18, 3:9,  4:13,  5:14,  6:19,  7:14,
    8:10,  9:15,10:27,11:22,12:29,13:16,14:15,
   15:17,16:18,17:15,18:20,19:15
}

ACTIVITY_TYPE = {
    'Office - Open Plan':'ACTIVITY_COMMON_OFFICE_OPEN',
    'Office - Enclosed':'ACTIVITY_COMMON_OFFICE_ENCLOSED',
    # … copy the rest from earlier …
}

def guess_type(name: str) -> str:
    n = name.upper()
    if 'OPEN DESK' in n: return 'Office - Open Plan'
    if n.startswith('LARGE OFFICE') or n.startswith('OFFICE'): return 'Office - Enclosed'
    if '<50' in n: return 'Storage <50 sq.ft.'
    if n.startswith(('MEN','WOMEN')) or 'RR ' in n: return 'Restrooms'
    if 'CORRIDORS' in n: return 'Corridor/Transition >=8 ft wide'
    if any(k in n for k in ('PHONE','FLEX ROOM','MED MEETING')): return 'Conference/Meeting/Multipurpose'
    if any(k in n for k in ('PANTRY','PREP PANTRY')): return 'Food Preparation'
    if 'ELEVATOR LOBBY' in n: return 'Lobby For Elevator'
    return 'Conference/Meeting/Multipurpose'

def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # 1) Parse spaces.csv → room→sqft
    spaces = {}
    for row in csv.DictReader(StringIO(spaces_csv), skipinitialspace=True):
        spaces[row['Room ID']] = float(row['SquareFootage'])

    # 2) Parse fixtures.csv and aggregate
    fixtures = defaultdict(lambda: defaultdict(int))
    watt = {}
    for row in csv.DictReader(StringIO(fixtures_csv), skipinitialspace=True):
        room = row['Room ID']
        fix  = row['Fixture Description']
        qty  = int(float(row['Quantity']))
        w    = float(row['Wattage'].rstrip('W').strip())
        fixtures[room][fix] += qty
        watt[fix] = w

    # 3) Build static header
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
        "  exterior lighting zone type = EXT_ZONE_UNSPECIFIED )",
    ]

    # 4) INTERIOR SPACE blocks
    for i, (room, sqft) in enumerate(spaces.items(), start=1):
        ctype = guess_type(room)
        cat   = CATEGORY_MAP[ctype]
        allowed = POWER_DENSITY[cat]
        total_w = sum(q * watt[f] for f,q in fixtures.get(room,{}).items())
        lines += [
            f"INTERIOR SPACE {i} (",
            f"  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>",
            "  space type = SPACE_INTERIOR_LIGHTING",
            f"  space allowed wattage = {allowed}",
            f"  space prop wattage = {int(total_w)}",
            f"  list position = {i}",
            "  allowance description = None",
            "  allowance type = ALLOWANCE_NONE",
            "  allowance floor area = 0",
            "  rcr perimeter = 0",
            "  rcr floor to workplane height = 0",
            "  rcr workplane to luminaire height = 0",
            f"  activity category number = {cat}",
            ")"
        ]

    # 5) FIXTURE blocks
    fid = len(spaces) + 1
    for i, room in enumerate(spaces, start=1):
        for fix, qty in fixtures.get(room,{}).items():
            w = int(watt[fix])
            lines += [
                f"FIXTURE {fid} (",
                f"  list position = {i}",
                "  fixture use type = FIXTURE_USE_INTERIOR",
                "  power adjustment factor = 0.000",
                "  paf desc = None",
                "  lamp wattage = 0.00",
                "  lighting type = LED",
                "  type of fixture = <||>",
                f"  description = <|{fix}|>",
                f"  fixture type = <|{fix}|>",
                f"  parent number = {i}",
                "  lamp ballast description = <||>",
                "  lamp type = Other",
                "  ballast = UNSPECIFIED_BALLAST",
                "  number of lamps = 1",
                f"  fixture wattage = {w}",
                f"  quantity = {qty}",
                ")"
            ]
            fid += 1

    # 6) ACTIVITY USE and static requirement blocks (copy your logic here)…
    #    …
    return "\n".join(lines)

# --- Streamlit UI ---

st.title("COMcheck Generator")
f_csv = st.file_uploader("Upload fixtures.csv", type="csv")
s_csv = st.file_uploader("Upload spaces.csv",   type="csv")

if f_csv and s_csv:
    comcheck_text = generate_comcheck(
        f_csv.getvalue().decode("utf-8-sig"),
        s_csv.getvalue().decode("utf-8-sig")
    )
    st.download_button(
        "Download COMcheck file",
        data=comcheck_text,
        file_name="comcheck_aggregated.txt",
        mime="text/plain"
    )
