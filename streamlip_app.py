import streamlit as st
import csv
import re
from io import StringIO
from collections import OrderedDict, defaultdict

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

# --- Helper functions ---
def guess_space_type(name: str) -> str:
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
    num = re.sub(r'[^\d.]', '', raw or '')
    return float(num) if num else 0.0

# --- Generation sections ---
def generate_header() -> list:
    return [
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


def generate_static_sections() -> list:
    return [
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


def generate_requirement_answers() -> list:
    lines = []
    for n in range(1, 21):
        req = '<|PR4_IECC2018_C_C103.2|>' if n == 1 else '<|EL26_IECC2018_C_C405.6|>'
        cat = 'INTERIOR LIGHTING' if n <= 13 else 'PROJECT'
        lines.extend([
            f"REQUIREMENT ANSWER {n} (",
            f"  requirement = {req}",
            f"  category = {cat}",
            "  exception name = <||>",
            "  location on plans = <||>",
            "  status = NOT_SATISFIED",
            ")"
        ])
    return lines


def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # Parse spaces.csv (ordered)
    reader_s = csv.DictReader(StringIO(spaces_csv), skipinitialspace=True)
    sf_key = next((k for k in reader_s.fieldnames if k.replace(' ', '').lower() == 'squarefootage'), None)
    if sf_key is None:
        raise ValueError(f"spaces.csv must have a 'SquareFootage' column; found {reader_s.fieldnames}")
    rooms = OrderedDict()
    for row in reader_s:
        rooms[row['Room ID']] = float(row[sf_key])
    # Map room -> interior index
    room_to_index = {room: idx for idx, room in enumerate(rooms, start=1)}
    
    # Parse fixtures.csv
    reader_f = csv.DictReader(StringIO(fixtures_csv), skipinitialspace=True)
    fixtures = defaultdict(lambda: defaultdict(lambda: {'qty': 0, 'watt': 0.0, 'allowance': {}}))
    for row in reader_f:
        room = row['Room ID']
        fix  = row['Fixture Description']
        qty  = int(float(row['Quantity']))
        w    = parse_wattage(row.get('Wattage', ''))
        fixtures[room][fix]['qty'] += qty
        fixtures[room][fix]['watt'] = w
        if row.get('AllowanceType'):
            fixtures[room][fix]['allowance'] = {
                'type': row.get('AllowanceType',''),
                'description': row.get('AllowanceDescription',''),
                'factor': row.get('PowerAllowanceFactor',''),
                'area': row.get('AllowanceFloorArea','')
            }

    lines = []
    # Header
    lines.extend(generate_header())

    # INTERIOR SPACE blocks
    for room, sqft in rooms.items():
        idx = room_to_index[room]
        ctype = guess_space_type(room)
        cat   = CATEGORY_MAP[ctype]
        allowed = POWER_DENSITY[cat]
        total_w = int(sum(info['qty'] * info['watt'] for info in fixtures.get(room, {}).values()))
        lines.extend([
            f"INTERIOR SPACE {idx} (",
            f"  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>",
            "  space type = SPACE_INTERIOR_LIGHTING",
            f"  space allowed wattage = {allowed}",
            f"  space prop wattage = {total_w}",
            f"  list position = {idx}",
            "  allowance description = None",
            "  allowance type = ALLOWANCE_NONE",
            "  allowance floor area = 0",
            "  rcr perimeter = 0",
            "  rcr floor to workplane height = 0",
            "  rcr workplane to luminaire height = 0",
            f"  activity category number = {cat}",
            ")"
        ])

    # FIXTURE blocks
    fixture_id_start = len(rooms) + 1
    fid = fixture_id_start
    for room in rooms:
        parent_i = room_to_index[room]
        for fix, info in fixtures.get(room, {}).items():
            lines.append(f"FIXTURE {fid} (")
            lines.extend([
                f"  list position = {parent_i}",
                "  fixture use type = FIXTURE_USE_INTERIOR",
                "  power adjustment factor = 0.000",
                "  paf desc = None",
                "  lamp wattage = 0.00",
                "  lighting type = LED",
                "  type of fixture = <||>",
                f"  description = <|{fix}|>",
                f"  fixture type = <|{fix}|>",
                f"  parent number = {parent_i}",
                "  lamp ballast description = <||>",
                "  lamp type = Other",
                "  ballast = UNSPECIFIED_BALLAST",
                "  number of lamps = 1",
                f"  fixture wattage = {int(info['watt'])}"
            ])
            alw = info.get('allowance', {})
            if alw:
                lines.extend([
                    f"  allowance type = {alw['type']}",
                    f"  allowance description = {alw['description']}",
                    f"  power allowance factor = {alw['factor']}",
                    f"  allowance floor area = {alw['area']}"
                ])
            lines.extend([
                f"  quantity = {info['qty']}",
                ")"
            ])
            fid += 1

    # ACTIVITY USE blocks
    for room, sqft in rooms.items():
        idx = room_to_index[room]
        ctype = guess_space_type(room)
        cat   = CATEGORY_MAP[ctype]
        act_code = ACTIVITY_TYPE[ctype]
        pd    = POWER_DENSITY[cat]
        lines.extend([
            f"ACTIVITY USE {idx} (",
            f"  key = {1000000000 + idx}",
            f"  activity type = {act_code}",
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
        ])

    # Static sections & requirements
    lines.extend(generate_static sections())
    lines.extend(generate_requirement_answers())

    return "\n".join(lines)

# --- Streamlit UI ---
st.set_page_config(page_title="TDA COMcheck Generator", layout="wide")
st.image("https://images.squarespace-cdn.com/content/v1/651344c15e9ed913545fbbf6/46e7dba5-6680-4ab9-9745-a0dc87f26000/TDA+LOGO%2C+JPEG.jpg?format=1500w", width=200)
st.title("TDA COMcheck Generator")

# Sample CSV templates
SAMPLE_FIXTURES = "Room ID,Fixture Description,Quantity,Wattage,AllowanceType,AllowanceDescription,PowerAllowanceFactor,AllowanceFloorArea\nOPEN DESK AREA - 17A01,TB-4,2,6 W,ALLOWANCE_NONE,,,"
SAMPLE_SPACES   = "Room ID,SquareFootage\nOPEN DESK AREA - 17A01,20"
col1, col2 = st.columns(2)
with col1:
    st.download_button("Fixtures template", SAMPLE_FIXTURES, "fixtures_template.csv", "text/csv")
with col2:
    st.download_button("Spaces template"  , SAMPLE_SPACES  , "spaces_template.csv"  , "text/csv")

# User inputs & generate
output_filename = st.text_input("Output filename:", "TDA_Generated ComCheck File.cck")
f_up = st.file_uploader("Upload fixtures.csv", type="csv")
s_up = st.file_uploader("Upload spaces.csv",   type="csv")
if f_up and s_up:
    try:
        txt = generate_comcheck(
            f_up.getvalue().decode("utf-8-sig"),
            s_up.getvalue().decode("utf-8-sig")
        )
        st.download_button("Download COMcheck file", txt, output_filename, "text/plain")
    except Exception as e:
        st.error(f"Error: {e}")
