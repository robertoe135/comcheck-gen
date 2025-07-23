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

def parse_wattage(s: str) -> float:
    num = re.sub(r'[^\d.]', '', s or '')
    return float(num) if num else 0.0

# Generate COMcheck content

def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # Parse spaces.csv
    reader_s = csv.DictReader(StringIO(spaces_csv))
    sf_keys = [k for k in reader_s.fieldnames or [] if k.replace(' ', '').lower() == 'squarefootage']
    if not sf_keys:
        raise ValueError(f"spaces.csv needs a SquareFootage column, found {reader_s.fieldnames}")
    sqm = sf_keys[0]
    spaces = {r['Room ID']: float(r[sqm]) for r in reader_s}

    # Parse fixtures.csv
    reader_f = csv.DictReader(StringIO(fixtures_csv))
    fixtures = defaultdict(lambda: defaultdict(int))
    watt_map = {}
    allowance = {}
    for r in reader_f:
        room = r['Room ID']; fix = r['Fixture Description']
        qty = int(float(r['Quantity'])); w = parse_wattage(r.get('Wattage',''))
        fixtures[room][fix] += qty; watt_map[fix] = w
        # decorative allowance support
        if r.get('AllowanceType'):
            allowance.setdefault((room,fix), {}).update({
                'type': r.get('AllowanceType',''),
                'description': r.get('AllowanceDescription',''),
                'factor': r.get('PowerAllowanceFactor',''),
                'area': r.get('AllowanceFloorArea','')
            })

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

    # Interior spaces
    for i,(room,sqft) in enumerate(spaces.items(),1):
        stype=guess_type(room); cat=CATEGORY_MAP[stype]; allow=POWER_DENSITY[cat]
        prop=int(sum(q*watt_map[f] for f,q in fixtures[room].items()))
        lines.extend([
            f'INTERIOR SPACE {i} (',
            f'  description = <|{room} ( Common Space Types:{stype} {sqft} sq.ft.)|>',
            '  space type = SPACE_INTERIOR_LIGHTING',
            f'  space allowed wattage = {allow}',
            f'  space prop wattage = {prop}',
            f'  list position = {i}',
            '  allowance description = None',
            '  allowance type = ALLOWANCE_NONE',
            '  allowance floor area = 0',
            '  rcr perimeter = 0',
            '  rcr floor to workplane height = 0',
            '  rcr workplane to luminaire height = 0',
            f'  activity category number = {cat}',
            ')'
        ])

    # Fixtures
    fid=len(spaces)+1
    for i,room in enumerate(spaces,1):
        for fix,qty in fixtures[room].items():
            w=int(watt_map.get(fix,0))
            lines.append(f'FIXTURE {fid} (')
            lines.extend([
                f'  list position = {i}',
                '  fixture use type = FIXTURE_USE_INTERIOR',
                '  power adjustment factor = 0.000',
                '  paf desc = None',
                '  lamp wattage = 0.00',
                '  lighting type = LED',
                '  type of fixture = <||>',
                f'  description = <|{fix}|>',
                f'  fixture type = <|{fix}|>',
                f'  parent number = {i}',
                '  lamp ballast description = <||>',
                '  lamp type = Other',
                '  ballast = UNSPECIFIED_BALLAST',
                '  number of lamps = 1',
                f'  fixture wattage = {w}'
            ])
            # decorative allowances
            key=(room,fix)
            if key in allowance:
                al=allowance[key]
                lines.extend([
                    f'  allowance type = {al["type"]}',
                    f'  allowance description = {al["description"]}',
                    f'  power allowance factor = {al["factor"]}',
                    f'  allowance floor area = {al["area"]}'
                ])
            lines.append(f'  quantity = {qty}')
            lines.append(')')
            fid+=1

    # Activity use
    for i,room in enumerate(spaces,1):
        stype=guess_type(room); cat=CATEGORY_MAP[stype]; dtype=ACTIVITY_TYPE[stype]; pd=POWER_DENSITY[cat]; sq=spaces[room]
        lines.extend([
            f'ACTIVITY USE {i} (',
            f'  key = {1000000000+i}',
            f'  activity type = {dtype}',
            f'  activity description = <|Common Space Types:{stype}|>',
            f'  area description = <|{room}|>',
            f'  power density = {pd}',
            '  ceiling height = 0',
            '  internal load = 1.95',
            f'  list position = {i}',
            '  area factor = 1',
            '  construction type = NON_RESIDENTIAL',
            f'  floor area = {sq}',
            ')'
        ])

    # Static sections
    lines.extend([
        'PROJECT 1 (','  project complete = FALSE',')',
        'WHOLE BLDG USE 2 (','  whole bldg type = WHOLE_BUILDING_INVALID_USE',
        '  key = 587260110','  whole bldg description = <||>','  area description = <||>',
        '  power density = 0','  internal load = 0','  ceiling height = 0',
        '  list position = 1','  construction type = NON_RESIDENTIAL','  floor area = 0',')',
        'EXTERIOR USE 1 (','  key = 1417866914','  exterior type = EXTERIOR_INVALID_USE',
        '  exterior description = <||>','  area description = <||>','  power density = 0',
        '  use quantity = 0','  quantity units = <||>','  is tradable = FALSE',')'
    ])

    # Requirements
    for n in range(1,21):
        lines.extend([
            f'REQUIREMENT ANSWER {n} (',
            '  requirement = <|PR4_IECC2018_C_C103.2|>' if n==1 else '  requirement = <|EL26_IECC2018_C_C405.6|>',
            '  category = INTERIOR LIGHTING' if n<=13 else '  category = PROJECT',
            '  exception name = <||>','  location on plans = <||>','  status = NOT_SATISFIED',')'
        ])

    return '\n'.join(lines)

# Streamlit UI
st.set_page_config(page_title='TDA COMcheck Generator', layout='wide')
st.image('https://images.squarespace-cdn.com/content/v1/651344c15e9ed913545fbbf6/46e7dba5-6680-4ab9-9745-a0dc87f26000/TDA+LOGO%2C+JPEG.jpg?format=1500w', width=200)
st.title('TDA COMcheck Generator')

# Sample CSV templates
S_F = 'Room ID,Fixture Description,Quantity,Wattage,AllowanceType,AllowanceDescription,PowerAllowanceFactor,AllowanceFloorArea\nOPEN DESK AREA - 17A01,TB-4,2,6 W,ALLOWANCE_NONE,,,'
S_S = 'Room ID,SquareFootage\nOPEN DESK AREA - 17A01,20'
col1, col2 = st.columns(2)
with col1:
    st.download_button('Fixtures template', S_F, 'fixtures_template.csv', 'text/csv')
with col2:
    st.download_button('Spaces template'  , S_S, 'spaces_template.csv'  , 'text/csv')

# File inputs
output_filename = st.text_input('Output filename:', 'TDA_Generated ComCheck File.cck')
f_up = st.file_uploader('Upload fixtures.csv', type='csv')
s_up = st.file_uploader('Upload spaces.csv',   type='csv')

if f_up and s_up:
    try:
        txt = generate_comcheck(f_up.getvalue().decode('utf-8-sig'), s_up.getvalue().decode('utf-8-sig'))
        st.download_button('Download COMcheck file', txt, output_filename, 'text/plain')
    except Exception as e:
        st.error(f'Error: {e}')
