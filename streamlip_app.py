import streamlit as st
import csv
import re
from io import StringIO
from collections import defaultdict

# --- Mapping tables - EXACT from original analysis ---
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
    'Electrical/Mechanical': 19,
    'Lobby - General': 20,  # Added based on official file
    'Computer Room': 21,    # Added based on official file
    'Storage >=50 - <=1000 sq.ft.': 22  # Added based on official file
}

# Power densities - Updated with new space types
POWER_DENSITY = {
    1: 0.82,   # Office - Open Plan
    2: 0.85,   # Office - Enclosed
    3: 0.43,   # Storage <50 sq.ft.
    4: 0.41,   # Corridor/Transition <8 ft wide
    5: 0.50,   # Corridor/Transition >=8 ft wide
    6: 0.75,   # Restrooms
    7: 0.89,   # Dining Area - Cafeteria/Fast Food
    8: 0.65,   # General Seating Area
    9: 0.52,   # Lobby For Elevator
    10: 0.92,  # Food Preparation
    11: 1.24,  # Classroom/Lecture/Training
    12: 0.93,  # Conference/Meeting/Multipurpose
    13: 0.49,  # Stairwell
    14: 0.75,  # Locker Room
    15: 0.72,  # Exercise Area
    16: 0.74,  # Copy/Print Room
    17: 0.43,  # Storage
    18: 0.89,  # Dining Area - General
    19: 0.95,  # Electrical/Mechanical
    20: 0.90,  # Lobby - General
    21: 1.16,  # Computer Room
    22: 0.43   # Storage >=50 - <=1000 sq.ft.
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
    'Electrical/Mechanical': 'ACTIVITY_COMMON_ELECTRICAL_MECHANICAL',
    'Lobby - General': 'ACTIVITY_COMMON_LOBBY',
    'Computer Room': 'ACTIVITY_COMMON_COMPUTER_ROOM',
    'Storage >=50 - <=1000 sq.ft.': 'ACTIVITY_COMMON_STORAGE_GT50_LT1000'
}

# Decorative fixture types and their allowances
DECORATIVE_FIXTURES = {
    # Fixtures that get decorative allowances in lobbies
    'TU': 'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES',
    'TU-2': 'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES',
    'TU-3': 'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES',
    'TT': 'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES',
    
    # Fixtures that get decorative allowances in other spaces
    'FFE-2': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'FFE-4': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'FFE-5': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'TM-1': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'TN': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'TN-3': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER',
    'TH-1': 'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER'
}

# Power allowance factors
POWER_ALLOWANCE_FACTORS = {
    'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES': 0.900,
    'ALLOWANCE_DECORATIVE_APPEARANCE_OTHER': 0.750
}

def guess_type(name: str) -> str:
    """Heuristic mapping from Room ID to space type."""
    n = name.upper()
    
    # Check for specific matches first
    if 'LOBBY' in n and 'ELEVATOR' in n:
        return 'Lobby For Elevator'
    elif any(x in n for x in ['ENTRANCE', 'PREFUNCTION', 'RECEPTION', 'BREAKOUT']) and 'LOBBY' in n:
        return 'Lobby - General'
    elif 'COMPUTER ROOM' in n or 'AV CLOSET' in n or 'ELEC ROOM' in n or 'MER ' in n:
        return 'Computer Room'
    elif 'STORAGE' in n and ('>=50' in n or '<=1000' in n):
        return 'Storage >=50 - <=1000 sq.ft.'
    elif 'STORAGE' in n or 'COAT CLOSET' in n or 'TRASH' in n:
        return 'Storage >=50 - <=1000 sq.ft.'
    elif 'OPEN DESK' in n:
        return 'Office - Open Plan'
    elif n.startswith('LARGE OFFICE') or n.startswith('OFFICE') or 'OFFICE' in n:
        return 'Office - Enclosed'
    elif '<50' in n:
        return 'Storage <50 sq.ft.'
    elif n.startswith(('MEN', 'WOMEN')) or 'RR ' in n or 'RESTROOM' in n:
        return 'Restrooms'
    elif 'CORRIDORS' in n:
        return 'Corridor/Transition >=8 ft wide'
    elif any(k in n for k in ('PHONE', 'FLEX ROOM', 'MED MEETING', 'CONFERENCE', 'INTERVIEW', 
                              'BOARDROOM', 'TALENT ROOM', 'MPR')):
        return 'Conference/Meeting/Multipurpose'
    elif any(k in n for k in ('PANTRY', 'PREP PANTRY', 'FOOD PREP')):
        return 'Food Preparation'
    elif 'ELEVATOR LOBBY' in n or 'ELEVATOR' in n:
        return 'Lobby For Elevator'
    elif 'LOBBY' in n:
        return 'Lobby - General'
    return 'Conference/Meeting/Multipurpose'

def parse_wattage(raw: str) -> float:
    """Extract numeric wattage from a string, stripping 'W' or any non-digit."""
    cleaned = re.sub(r'[^\d.]', '', raw)
    return float(cleaned) if cleaned else 0.0

def get_decorative_allowance_for_fixture(fixture_type: str, space_type: str) -> tuple:
    """
    Returns (allowance_type, allowance_description, power_factor) or (None, None, None)
    """
    if fixture_type not in DECORATIVE_FIXTURES:
        return None, None, None
    
    allowance_type = DECORATIVE_FIXTURES[fixture_type]
    
    # Check if this allowance type is appropriate for the space
    if allowance_type == 'ALLOWANCE_DECORATIVE_APPEARANCE_LOBBIES':
        # Only apply to lobby spaces
        if 'Lobby' in space_type:
            return (allowance_type, 
                   'Decorative Appearance in lobbbies',  # Note: typo is intentional to match official
                   POWER_ALLOWANCE_FACTORS[allowance_type])
    else:
        # Apply to non-lobby spaces
        if 'Lobby' not in space_type:
            return (allowance_type,
                   'Decorative Appearance (not lobbies)',
                   POWER_ALLOWANCE_FACTORS[allowance_type])
    
    return None, None, None

def generate_comcheck(fixtures_csv: str, spaces_csv: str) -> str:
    # Parse spaces.csv
    reader_s = csv.DictReader(StringIO(spaces_csv), skipinitialspace=True)
    sf_keys = [k for k in reader_s.fieldnames if k.replace(" ", "").lower() == "squarefootage"]
    if not sf_keys:
        raise ValueError(f"spaces.csv must have a 'SquareFootage' column; found {reader_s.fieldnames}")
    sf_key = sf_keys[0]
    spaces = {row['Room ID']: int(float(row[sf_key])) for row in reader_s}

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

    # Build EXACT header from original file
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
        "  exterior lighting zone = 4 ",
        "  exterior lighting zone type = EXT_ZONE_UNSPECIFIED )"
    ]

    # Track decorative allowances by space
    space_decorative_allowances = {}
    
    # First pass: identify decorative fixtures and calculate allowances
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        ctype = guess_type(room)
        room_fixtures = fixtures.get(room, {})
        
        # Calculate decorative allowances for this space
        total_decorative_area = 0
        for fix_type, qty in room_fixtures.items():
            allowance_type, _, _ = get_decorative_allowance_for_fixture(fix_type, ctype)
            if allowance_type:
                # For decorative fixtures, the allowance area is the room area
                total_decorative_area = sqft
                break  # Only need one decorative fixture to apply allowance to whole space
        
        space_decorative_allowances[idx] = total_decorative_area

    # INTERIOR SPACE blocks with allowance calculations
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP.get(ctype, 12)  # Default to conference if not found
        power_density = POWER_DENSITY.get(cat, 0.93)
        
        # Calculate base allowed wattage
        base_allowed = int(power_density * sqft)
        
        # Add decorative allowance if applicable
        decorative_area = space_decorative_allowances.get(idx, 0)
        if decorative_area > 0:
            # Check which type of decorative allowance applies
            room_fixtures = fixtures.get(room, {})
            for fix_type in room_fixtures:
                allowance_type, _, power_factor = get_decorative_allowance_for_fixture(fix_type, ctype)
                if allowance_type:
                    # Add decorative allowance: area * power_density * (1 - power_factor)
                    decorative_allowance = int(decorative_area * power_density * (1 - power_factor))
                    base_allowed += decorative_allowance
                    break
        
        total_w = sum(q * watt_map[f] for f, q in fixtures.get(room, {}).items())
        
        lines += [
            f"INTERIOR SPACE {idx} (",
            f"  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>",
            "  space type = SPACE_INTERIOR_LIGHTING",
            f"  space allowed wattage = {base_allowed}",
            f"  space prop wattage = {int(total_w)}",
            f"  list position = {idx}",
            "  allowance description = None",
            "  allowance type = ALLOWANCE_NONE",
            "  allowance floor area = 0",
            "  rcr perimeter = 0",
            "  rcr floor to workplane height = 0",
            "  rcr workplane to luminaire height = 0",
            f"  activity category number = {cat} )"
        ]

    # FIXTURE blocks with decorative allowance attributes
    fid = 1
    list_pos = 1
    for idx, room in enumerate(spaces, start=1):
        room_type = guess_type(room)
        room_sqft = spaces[room]
        
        for fix, qty in fixtures.get(room, {}).items():
            w = int(watt_map.get(fix, 0))
            
            # Check if this fixture gets decorative allowance
            allowance_type, allowance_desc, power_factor = get_decorative_allowance_for_fixture(fix, room_type)
            
            lines += [
                f"FIXTURE {fid} (",
                f"  list position = {list_pos}",
                "  fixture use type = FIXTURE_USE_INTERIOR",
                "  power adjustment factor = 0.000",
                "  paf desc = None",
                "  lamp wattage = 0.00",
                "  lighting type = LED",
                f"  type of fixture = <|{fix}|>",
                "  description = <||>",
                f"  fixture type = <|{fix}|>",
                f"  parent number = {idx}",
                "  lamp ballast description = <||>",
                "  lamp type = Other",
                "  ballast = UNSPECIFIED_BALLAST",
                "  number of lamps = 1",
                f"  fixture wattage = {w}"
            ]
            
            # Add decorative allowance fields if applicable
            if allowance_type:
                lines += [
                    f"  allowance type = {allowance_type}",
                    f"  allowance description = {allowance_desc}",
                    f"  power allowance factor = {power_factor:.3f}",
                    f"  allowance floor area = {room_sqft}"
                ]
            
            lines.append(f"  quantity = {qty} )")
            
            fid += 1
            list_pos += 1

    # PROJECT section - exact from original
    lines += [
        "PROJECT 1 (",
        "  project complete = FALSE",
        "  )"
    ]

    # ACTIVITY USE blocks - exact format from original
    for idx, room in enumerate(spaces, start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP.get(ctype, 12)
        dtype = ACTIVITY_TYPE.get(ctype, 'ACTIVITY_COMMON_CONFERENCE_HALL')
        power_density = POWER_DENSITY.get(cat, 0.93)
        sqft = spaces[room]
        # Generate a consistent key based on room name
        key_val = abs(hash(room)) % 2000000000 + 500000000
        
        lines += [
            f"ACTIVITY USE {idx} (",
            f"  key = {key_val}",
            f"  activity type = {dtype}",
            f"  activity description = <|Common Space Types:{ctype}|>",
            f"  area description = <|{room}|>",
            f"  power density = {power_density}",
            "  ceiling height = 0",
            "  internal load = 1.95",
            f"  list position = {idx}",
            "  area factor = 1",
            "  construction type = NON_RESIDENTIAL",
            f"  floor area = {sqft} )"
        ]

    # WHOLE BLDG USE and EXTERIOR USE - exact from original
    lines += [
        "WHOLE BLDG USE 1 (",
        "  whole bldg type = WHOLE_BUILDING_INVALID_USE",
        "  key = 1545582262",
        "  whole bldg description = <||>",
        "  area description = <||>",
        "  power density = 0",
        "  internal load = 0",
        "  ceiling height = 0",
        "  list position = 1",
        "  construction type = NON_RESIDENTIAL",
        "  floor area = 0 )",
        "EXTERIOR USE 1 (",
        "  key = 1791777704",
        "  exterior type = EXTERIOR_INVALID_USE",
        "  exterior description = <||>",
        "  area description = <||>",
        "  power density = 0",
        "  use quantity = 0",
        "  quantity units = <||>",
        "  is tradable = FALSE )"
    ]

    # REQUIREMENT ANSWER blocks - exact from original
    requirement_codes = [
        "PR4_IECC2018_C_C103.2",
        "FI17_IECC2018_C_C303.3_C408.2.5.2", 
        "EL18_NYSTRETCH_NYC_IECC2018_C_C405.2.1_C405.2.1.1",
        "EL19_IECC2018_C_C405.2.1.2",
        "EL20_IECC2018_C_C405.2.1.3",
        "EL21_IECC2018_C_C405.2.2_C405.2.2.1_C405.2.2.2",
        "EL22_IECC2018_C_C405.2.2.2",
        "EL23_NYSTRETCH_IECC2018_C_C405.2.3_C405.2.3.1_C405.2.3.2",
        "EL26_IECC2018_C_C405.2.4",
        "EL27_IECC2018_C_C405.2.4",
        "EL6_NYSTRETCH_NYC_IECC2018_C_C405.1.1",
        "FI18_IECC2018_C_C405.3.1",
        "FI33_IECC2018_C_C408.3"
    ]
    
    for n in range(1, len(requirement_codes) + 1):
        lines += [
            f"REQUIREMENT ANSWER {n} (",
            f"  requirement = <|{requirement_codes[n-1]}|>",
            "  category = INTERIOR LIGHTING",
            "  exception name = <||>",
            "  location on plans = <||>",
            "  status = NOT_SATISFIED )"
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

st.markdown("#### Download sample CSV templates to get started. This only works with NYC IECC 2020 at this time.")
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
        st.success("✅ ComCheck file generated successfully!")
    except Exception as e:
        st.error(f"Error generating COMcheck: {e}")
