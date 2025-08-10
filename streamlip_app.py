import streamlit as st
import csv
import re
from io import StringIO
from collections import defaultdict

st.set_page_config(page_title="COMcheck CCK Builder (Refactored)", layout="wide")

# -------- Utilities --------
def parse_cck_blocks(text, section):
    pattern = re.compile(rf"{section}\s+(\d+)\s+\(", re.MULTILINE)
    matches = list(pattern.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        content = text[start:end]
        blocks.append((int(m.group(1)), content))
    return blocks

def kv_pairs(block_text):
    out = {}
    for line in block_text.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip()
    return out

def extract_header_and_tail(txt):
    # Keep everything before the first INTERIOR SPACE / ACTIVITY USE
    # and everything after the last of those sections
    first = None
    last = 0
    for m in re.finditer(r"(INTERIOR SPACE|ACTIVITY USE)\s+\d+\s+\(", txt):
        if first is None:
            first = m.start()
        last = m.end()
    if first is None:
        return txt, "", ""
    header = txt[:first]
    tail = txt[last:]
    return header, txt[first:last], tail

# Approved space types
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

# Default LPDs in W/ft² (edit in UI)
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
    if 'CORRIDOR' in n:
        return 'Corridor/Transition >=8 ft wide'
    if 'PHONE' in n:
        return 'Copy/Print Room'  # conservative default
    return 'Office - Enclosed'

def build_sections(spaces, fixtures, watt_map, lpd_map):
    lines = []

    # INTERIOR SPACE blocks
    for idx, (room, sqft) in enumerate(spaces.items(), start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP[ctype]
        pd = float(lpd_map.get(ctype, DEFAULT_LPD[ctype]))
        total_w = sum(q * float(watt_map.get(f, 0)) for f, q in fixtures.get(room, {}).items())
        allowed_watts = int(round(float(sqft) * pd))

        lines += [
            f"INTERIOR SPACE {idx} (",
            f"  description = <|{room} ( Common Space Types:{ctype} {sqft} sq.ft.)|>",
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
    for idx, room in enumerate(spaces, start=1):
        ctype = guess_type(room)
        cat = CATEGORY_MAP[ctype]
        dtype = ACTIVITY_TYPE[ctype]
        pd = float(lpd_map.get(ctype, DEFAULT_LPD[ctype]))
        sqft = float(spaces[room])
        lines += [
            f"ACTIVITY USE {idx} (",
            f"  key = {1000000000 + idx}",
            f"  activity type = {dtype}",
            f"  activity description = <|Common Space Types:{ctype}|>",
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

def normalize_act_list_positions(cck_text):
    # Ensure ACTIVITY USE list positions == their index
    blocks = list(re.finditer(r"(ACTIVITY USE\s+(\d+)\s+\()(.+?)(?=(?:\n[A-Z ]+\s+\d+\s+\()|$)", cck_text, flags=re.DOTALL))
    chunks = []
    last_end = 0
    for m in blocks:
        chunks.append(cck_text[last_end:m.start()])
        idx = int(m.group(2))
        body = m.group(3)
        body_fixed = re.sub(r"(?:^|\n)\s*list position\s*=\s*\d+", "\n  list position = {}".format(idx), body, count=1)
        chunks.append("ACTIVITY USE {} (".format(idx) + body_fixed)
        last_end = m.end()
    chunks.append(cck_text[last_end:])
    return "".join(chunks)

def validator(cck_text):
    # Check duplicates and area matches
    errors = []

    def extract_blocks(text, section):
        pattern = re.compile(rf"{section}\s+(\d+)\s+\(", re.MULTILINE)
        matches = list(pattern.finditer(text))
        blocks = []
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            content = text[start:end]
            blocks.append((int(m.group(1)), content))
        return blocks

    def kvs(block_text):
        out = {}
        for line in block_text.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip()
        return out

    spaces = extract_blocks(cck_text, "INTERIOR SPACE")
    acts = extract_blocks(cck_text, "ACTIVITY USE")

    # List position uniqueness
    sp_pos = []
    ac_pos = []
    for i, b in spaces:
        kv = kvs(b)
        sp_pos.append(int(kv.get("list position", "0")))
    for i, b in acts:
        kv = kvs(b)
        ac_pos.append(int(kv.get("list position", "0")))
    if len(sp_pos) != len(set(sp_pos)):
        errors.append("Duplicate INTERIOR SPACE list positions detected.")
    if len(ac_pos) != len(set(ac_pos)):
        errors.append("Duplicate ACTIVITY USE list positions detected.")

    # Area matching by position (desc sq.ft. vs ACTIVITY USE floor area)
    def desc_area(desc):
        m = re.search(r"(\d+(?:\.\d+)?)\s*sq\.ft\.\)\|>", desc or "")
        return float(m.group(1)) if m else None

    sp_map = {}
    for i, b in spaces:
        kv = kvs(b)
        pos = int(kv.get("list position", "0"))
        sp_map[pos] = desc_area(kv.get("description", ""))

    for i, b in acts:
        kv = kvs(b)
        pos = int(kv.get("list position", "0"))
        fa = kv.get("floor area", "0").split()[0]
        try:
            fa = float(fa)
        except:
            fa = None
        if pos in sp_map and sp_map[pos] is not None and fa is not None and sp_map[pos] != fa:
            errors.append(f"Area mismatch at position {pos}: INTERIOR={sp_map[pos]} vs ACTIVITY={fa}")

    return errors

# -------- UI --------
st.title("Refactored COMcheck Generator (Fixes Allowances & List Positions)")

with st.sidebar:
    st.header("Inputs")
    f_uploaded = st.file_uploader("Fixtures CSV (room,fixture,quantity,watt)", type=["csv"])
    s_uploaded = st.file_uploader("Spaces CSV (room,floor_area)", type=["csv"])
    official_cck = st.file_uploader("Optional: Official reference CCK (to clone header/tail)", type=["cck","txt"])

    st.markdown("---")
    st.subheader("LPD overrides (W/ft²)")
    lpd_map = {}
    for name in SPACE_TYPES:
        lpd_map[name] = st.number_input(f"{name}", value=float(DEFAULT_LPD[name]), step=0.01, format="%.2f")

    output_filename = st.text_input("Output filename", value="Generated_ComCheck_refactored.cck")

def load_spaces(csv_text):
    reader = csv.DictReader(StringIO(csv_text))
    spaces = {}
    for row in reader:
        room = row.get("room") or row.get("Room") or row.get("area_description") or row.get("Area")
        area = row.get("floor_area") or row.get("sqft") or row.get("Floor Area")
        if not room or not area:
            continue
        try:
            spaces[room.strip()] = float(area)
        except:
            pass
    return spaces

def load_fixtures(csv_text):
    reader = csv.DictReader(StringIO(csv_text))
    fixtures = defaultdict(lambda: defaultdict(int))
    watt_map = {}
    for row in reader:
        room = (row.get("room") or row.get("Room") or "").strip()
        fix = (row.get("fixture") or row.get("Fixture") or "").strip()
        qty = row.get("quantity") or row.get("qty") or "0"
        watt = row.get("watt") or row.get("watts") or row.get("W") or "0"
        if room and fix:
            try:
                fixtures[room][fix] += int(float(qty))
                watt_map[fix] = float(watt)
            except:
                continue
    return fixtures, watt_map

def generate_from_inputs(spaces, fixtures, watt_map, lpd_map, header_text=None, tail_text=None):
    # Ensure stable order
    spaces = dict(sorted(spaces.items(), key=lambda x: x[0]))
    lines = []

    # Header
    if header_text:
        lines.append(header_text.rstrip("\n"))

    # Sections
    section_lines = build_sections(spaces, fixtures, watt_map, lpd_map)
    lines.extend(section_lines)

    # Tail
    if tail_text:
        lines.append(tail_text.lstrip("\n"))

    out = "\n".join(lines)
    out = normalize_act_list_positions(out)
    return out

if 'f_uploaded' not in globals():
    f_uploaded = None
if 's_uploaded' not in globals():
    s_uploaded = None

if f_uploaded and s_uploaded:
    try:
        spaces = load_spaces(s_uploaded.getvalue().decode("utf-8-sig"))
        fixtures, watt_map = load_fixtures(f_uploaded.getvalue().decode("utf-8-sig"))

        header_txt = tail_txt = None
        if official_cck:
            base_txt = official_cck.getvalue().decode("utf-8", errors="ignore")
            header_txt, _mid, tail_txt = extract_header_and_tail(base_txt)

        cck_text = generate_from_inputs(spaces, fixtures, watt_map, lpd_map, header_txt, tail_txt)
        errs = validator(cck_text)
        if errs:
            st.error("Validation issues:\n- " + "\n- ".join(errs))
        st.download_button("Download COMcheck file", data=cck_text, file_name=output_filename, mime="text/plain")
        st.code(cck_text[:2000])
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Upload your Fixtures CSV and Spaces CSV to generate a COMcheck .cck file. Optionally add an Official CCK to clone headers/trailers.")
