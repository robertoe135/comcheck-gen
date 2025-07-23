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

# Heuristic mapping from room name to space type
def guess_type(name: str) -> str:
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

# Robust wattage parsing
def parse_wattage(raw: str) -> float:
    num = re.sub(r'[^\d.]', '', raw or '')
    return float(num) if num else 0.0

# Main COMcheck generation function
def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # Parse spaces.csv into ordered rooms list
    reader_s = csv.DictReader(StringIO(spaces_csv), skipinitialspace=True)
    sf_key = next((k for k in reader_s.fieldnames if k.replace(' ', '').lower() == 'squarefootage'), None)
    if sf_key is None:
        raise ValueError(f"spaces.csv must have a 'SquareFootage' column; found {reader_s.fieldnames}")
    rooms = []
    spaces = {}
    for row in reader_s:
        room = row['Room ID']
        sqft = float(row[sf_key])
        rooms.append(room)
        spaces[room] = sqft
    room_index = {room: i for i, room in enumerate(rooms, start=1)}

    # Parse fixtures.csv and collect allowances
    reader_f = csv.DictReader(StringIO(fixtures_csv), skipinitialspace=True)
    fixtures = defaultdict(lambda: defaultdict(int))
    watt_map = {}
    allowances = {}
    for row in reader_f:
        room = row['Room ID']
        fix  = row['Fixture Description']
        qty  = int(float(row['Quantity']))
        w    = parse_wattage(row.get('Wattage',''))
        fixtures[room][fix] += qty
        watt_map[fix] = w
        # Collect decorative allowances if present
        if row.get('AllowanceType'):
            allowances[(room, fix)] = {
                'type': row.get('AllowanceType',''),
                'description': row.get('AllowanceDescription',''),
                'factor': row.get('PowerAllowanceFactor',''),
                'area': row.get('AllowanceFloorArea','')
            }

    lines = []
    # Header
    lines.extend([
        'WARNING: Do Not Modify This File!',
        'Check 24.1.6 Data File',
        'CONTROL 1 (',
        '  code = CEZ_NYSTRETCH_NYC_IECC2018',
        '  compliance mode = UA',
        '  version = 24.1.6 )',
        'LOCATION 1 (',
        '  state = New York',
        '  city = New York )',
        'BUILDING 1 (',
        '  project type = NEW_CONSTRUCTION',
        '  bldg use type = ACTIVITY',
        '  feet bldg height = 0.000',
        '  number of stories = 1',
        '  is nonresidential conditioning = TRUE',
        '  is residential conditioning = FALSE',
        '  is semiheated conditioning = FALSE',
        '  conditioning = HEATING_AND_COOLING)',
        'ENVELOPE 1 (',
        '  use orient details = TRUE',
        '  use vlt details = FALSE',
        '  use cool roof performance details = FALSE',
        '  air barrier compliance type = AIR_BARRIER_OPTION_UNKNOWN',
        '  apply window pct allowance for daylighting = FALSE',
        '  apply skylight pct allowance for daylighting = FALSE )',
        'LIGHTING 1 (',
        '  exterior lighting zone = 0 ',
        '  exterior lighting zone type = EXT_ZONE_UNSPECIFIED )'
    ])

    # INTERIOR SPACE blocks
    for room in rooms:
        idx = room_index[room]
        ctype = guess_type(room)
        cat   = CATEGORY_MAP[ctype]
        allowed = POWER_DENSITY[cat]
        total_w = int(sum(q * watt_map[f] for f, q in fixtures.get(room, {}).items()))
        sqft = spaces[room]
        lines.extend([
            f'INTERIOR SPACE {idx} (',
            f'  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>',
            '  space type = SPACE_INTERIOR_LIGHTING',
            f'  space allowed wattage = {allowed}',
            f'  space prop wattage = {total_w}',
            f'  list position = {idx}',
            '  allowance description = None',
            '  allowance type = ALLOWANCE_NONE',
            '  allowance floor area = 0',
            '  rcr perimeter = 0',
            '  rcr floor to workplane height = 0',
            '  rcr workplane to luminaire height = 0',
            f'  activity category number = {cat}',
            ')'  # Closing bracket for INTERIOR SPACE
        ])

    # FIXTURE blocks
    fid_start = len(rooms) + 1
    fid = fid_start
    for room in rooms:
        idx = room_index[room]
        for fix, qty in fixtures[room].items():
            w = int(watt_map.get(fix, 0))
            lines.append(f'FIXTURE {fid} (')
            lines.extend([
                f'  list position = {idx}',
                '  fixture use type = FIXTURE_USE_INTERIOR',
                '  power adjustment factor = 0.000',
                '  paf desc = None',
                '  lamp wattage = 0.00',
                '  lighting type = LED',
                '  type of fixture = <||>',
                f'  description = <|{fix}|>',
                f'  fixture type = <|{fix}|>',
                f'  parent number = {idx}',
                '  lamp ballast description = <||>',
                '  lamp type = Other',
                '  ballast = UNSPECIFIED_BALLAST',
                '  number of lamps = 1',
                f'  fixture wattage = {w}'
            ])
            # Decorative allowances if present
            key = (room, fix)
            if key in allowances:
                al = allowances[key]
                lines.extend([
                    f'  allowance type = {al["type"]}',
                    f'  allowance description = {al["description"]}',
                    f'  power allowance factor = {al["factor"]}',
                    f'  allowance floor area = {al["area"]}'
                ])
            lines.append(f'  quantity = {qty}')
            lines.append(')')  # Closing bracket for FIXTURE
            fid += 1

    # ACTIVITY USE blocks
    for room in rooms:
        idx = room_index[room]
        ctype = guess_type(room)
        cat   = CATEGORY_MAP[ctype]
        dtype = ACTIVITY_TYPE[ctype]
        pd    = POWER_DENSITY[cat]
        sqft = spaces[room]
        lines.extend([
            f'ACTIVITY USE {idx} (',
            f'  key = {1000000000 + idx}',
            f'  activity type = {dtype}',
            f'  activity description = <|Common Space Types:{ctype}|>',
            f'  area description = <|{room}|>',
            f'  power density = {pd}',
            '  ceiling height = 0',
            '  internal load = 1.95',
            f'  list position = {idx}',
            '  area factor = 1',
            '  construction type = NON_RESIDENTIAL',
            f'  floor area = {sqft}',
            ')'  # Closing bracket for ACTIVITY USE
        ])

    # PROJECT / WHOLE BLDG USE / EXTERIOR USE
    lines.extend([
        'PROJECT 1 (',
        '  project complete = FALSE',
        ')',
        'WHOLE BLDG USE 2 (',
        '  whole bldg type = WHOLE_BUILDING_INVALID_USE',
        '  key = 587260110',
        '  whole bldg description = <||>',
        '  area description = <||>',
        '  power density = 0',
        '  internal load = 0',
        '  ceiling height = 0',
        '  list position = 1',
        '  construction type = NON_RESIDENTIAL',
        '  floor area = 0',
        ')',
        'EXTERIOR USE 1 (',
        '  key = 1417866914',
        '  exterior type = EXTERIOR_INVALID_USE',
        '  exterior description = <||>',
        '  area description = <||>',
        '  power density = 0',
        '  use quantity = 0',
        '  quantity units = <||>',
        '  is tradable = FALSE',
        ')'  # Closing bracket
    ])

    # REQUIREMENT ANSWER blocks
    for n in range(1, 21):
        requirement = '<|PR4_IECC2018_C_C103.2|>' if n == 1 else '<|EL26_IECC2018_C_C405.6|>'
        category    = 'INTERIOR LIGHTING' if n <= 13 else 'PROJECT'
        lines.extend([
            f'REQUIREMENT ANSWER {n} (',
            f'  requirement = {requirement}',
            f'  category = {category}',
            '  exception name = <||>',
            '  location on plans = <||>',
            '  status = NOT_SATISFIED',
            ')'  # Closing bracket
        ])

    return '\n'.join(lines)

# --- Streamlit UI ---
st.set_page_config(page_title='TDA COMcheck Generator', layout='wide')
st.image('https://images.squarespace-cdn.com/content/v1/651344c15e9ed913545fbbf6/46e7dba5-6680-4ab9-9745-a0dc87f26000/TDA+LOGO%2C+JPEG.jpg?format=1500w', width=200)
st.title('TDA COMcheck Generator')

# Sample CSV templates
SAMPLE_FIXTURES = 'Room ID,Fixture Description,Quantity,Wattage,AllowanceType,AllowanceDescription,PowerAllowanceFactor,AllowanceFloorArea\nOPEN DESK AREA - 17A01,TB-4,2,6 W,ALLOWANCE_NONE,,,'
SAMPLE_SPACES   = 'Room ID,SquareFootage\nOPEN DESK AREA - 17A01,20'
col1, col2 = st.columns(2)
with col1:
    st.download_button('Fixtures template', SAMPLE_FIXTURES, 'fixtures_template.csv', 'text/csv')
with col2:
    st.download_button('Spaces template',   SAMPLE_SPACES,   'spaces_template.csv',   'text/csv')

# User file inputs
output_filename = st.text_input('Output filename:', 'TDA_Generated ComCheck File.cck')
f_up = st.file_uploader('Upload fixtures.csv', type='csv')
s_up = st.file_uploader('Upload spaces.csv',   type='csv')

# Generate and download
if f_up and s_up:
    try:
        comcheck_text = generate_comcheck(
            f_up.getvalue().decode('utf-8-sig'),
            s_up.getvalue().decode('utf-8-sig')
        )
        st.download_button('Download COMcheck file', comcheck_text, output_filename, 'text/plain')
    except Exception as e:
        st.error(f'Error generating COMcheck: {e}')
