"""Search-based apartment interior layout. Needs no training data.

Each apartment is built from an architectural grammar that is correct by
construction (entrance off the common corridor, kitchen beside living,
bedrooms on the outside wall off a passage, master bath beside the master
bedroom). The search enumerates the open choices -- kitchen on the facade or
beside the entrance, mirrored or not, wet-band depth, entrance-band depth --
and scores every candidate with a rule-based cost (room sizes and proportions,
minimum widths, door paths, daylight). Variants are the best candidates of
distinct arrangements.

Canonical frame: unit occupies (0, 0)-(width, depth); the common corridor runs
along y = 0 and the main facade along y = depth.
"""

from itertools import product
from typing import Dict, List, Tuple

Rect = Tuple[float, float, float, float]  # x0, y0, x1, y1

HABITABLE = {"living", "dining", "kitchen", "bedroom", "master_bedroom"}
SHAFT_OK = {"kitchen", "dining"}  # may ventilate via a duct when no outside wall
DOOR = 0.9  # minimum shared wall for a door
PASSAGE = 1.1

# type: (min short side, max aspect ratio)
_SHAPE = {
    "entrance": (1.2, 2.5), "living": (3.0, 1.8), "dining": (2.4, 1.8),
    "kitchen": (2.1, 2.2), "utility": (1.0, 2.8), "master_bedroom": (3.0, 1.5),
    "bedroom": (2.7, 1.6), "master_bathroom": (1.5, 2.0), "bathroom": (1.5, 2.0),
    "corridor": (1.0, 99.0), "storage": (0.8, 99.0),
}
# A room of this type needs a door from one of these room types.
ACCESS_FROM = {
    "bedroom": {"corridor", "living", "dining", "entrance"},
    "master_bedroom": {"corridor", "living", "dining", "entrance"},
    "bathroom": {"corridor", "living", "dining", "entrance", "bedroom", "master_bedroom"},
    "corridor": {"living", "dining", "entrance"},
    "dining": {"living", "entrance"},
    "kitchen": {"dining", "living", "entrance"},
    "utility": {"kitchen"},
    "master_bathroom": {"master_bedroom"},
    "storage": {"corridor", "entrance"},
    "living": {"entrance"},
}


def room_program(bedrooms: int) -> Dict[str, float]:
    """Target areas (m^2) for the fixed rooms; living/bedrooms take the rest."""
    program = {"entrance": 3.5 if bedrooms < 3 else 4.5,
               "kitchen": {1: 6.5, 2: 7.5}.get(bedrooms, 9.0),
               "master_bedroom": 12.5, "bedroom": 10.5, "bathroom": 3.6,
               "master_bathroom": 4.0, "utility": 2.5, "living": 13.0 + 1.5 * bedrooms}
    if bedrooms >= 3:
        program["dining"] = 9.0
    return program


def bathroom_count(bedrooms: int) -> int:
    return max(1, bedrooms - (1 if bedrooms >= 3 else 0))


def frontage_needed(bedrooms: int) -> float:
    """Outside-wall length (m) the facade rooms need, with ~15% slack."""
    return 1.15 * (3.4 + 3.2 + 2.9 * (bedrooms - 1) + (2.4 if bedrooms >= 2 else 0.0))


def _shared(a: Rect, b: Rect) -> float:
    if abs(a[2] - b[0]) < 1e-6 or abs(b[2] - a[0]) < 1e-6:
        return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    if abs(a[3] - b[1]) < 1e-6 or abs(b[3] - a[1]) < 1e-6:
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    return 0.0


def _exterior(r: Rect, width: float, depth: float, sides: Tuple[str, ...]) -> float:
    length = r[2] - r[0] if abs(r[3] - depth) < 1e-6 else 0.0
    if "left" in sides and abs(r[0]) < 1e-6:
        length = max(length, r[3] - r[1])
    if "right" in sides and abs(r[2] - width) < 1e-6:
        length = max(length, r[3] - r[1])
    return length


def _borrows_light(kind: str, r: Rect, rooms: List[Tuple[str, Rect]],
                   width: float, depth: float, sides: Tuple[str, ...]) -> bool:
    """Kitchen lit/vented through an outside utility; dining open to living."""
    donor, opening = {"kitchen": ("utility", 1.2), "dining": ("living", 2.4)}.get(kind, (None, 0))
    return any(t == donor and _shared(r, o) >= opening and _exterior(o, width, depth, sides) >= 1.2
               for t, o in rooms)


def score(rooms: List[Tuple[str, Rect]], bedrooms: int, width: float, depth: float,
          sides: Tuple[str, ...] = ()) -> List[Tuple[float, str]]:
    """Itemised penalties for broken design rules; an empty list is a clean plan."""
    targets = room_program(bedrooms)
    items: List[Tuple[float, str]] = []
    for kind, r in rooms:
        w, h = r[2] - r[0], r[3] - r[1]
        short, long_ = min(w, h), max(w, h)
        min_side, max_aspect = _SHAPE[kind]
        if short < 0.1:
            items.append((1000, f"no room left for the {kind}"))
            continue
        if kind in targets and kind != "living":
            items.append((4 * (w * h / targets[kind] - 1) ** 2, f"{kind} area off target"))
        if short < min_side - 1e-6:
            gap = min_side - short
            items.append((60 * gap ** 2 + 30 * gap, f"{kind} narrower than {min_side} m"))
        if long_ / short > max_aspect:
            items.append((6 * (long_ / short - max_aspect) ** 2, f"{kind} too elongated"))
        if kind in HABITABLE:
            facade = _exterior(r, width, depth, sides)
            if facade < 1.2 and not _borrows_light(kind, r, rooms, width, depth, sides):
                items.append((5 if kind in SHAFT_OK else 40 + 20 * (1.2 - facade),
                              f"{kind} has no outside wall"
                              + (" (needs a ventilation shaft)" if kind in SHAFT_OK else "")))
        sources = ACCESS_FROM.get(kind)
        if sources:
            best = max((_shared(r, o) for t, o in rooms if t in sources and o is not r), default=0.0)
            if best < DOOR:
                items.append((50 + 20 * (DOOR - best), f"{kind} has no door to {'/'.join(sorted(sources))}"))
    entrance = next(r for t, r in rooms if t == "entrance")
    if entrance[1] > 1e-6 or entrance[2] - entrance[0] < 1.0:
        items.append((80, "entrance does not open off the common corridor"))
    return [(round(c, 2), why) for c, why in items if c >= 0.05]


def _split(x0: float, x1: float, weights: List[float]) -> List[Tuple[float, float]]:
    total, edges, x = sum(weights), [], x0
    for w in weights:
        edges.append((x, x + (x1 - x0) * w / total))
        x = edges[-1][1]
    return edges


def build(bedrooms: int, width: float, depth: float, kitchen_on_facade: bool,
          wet_depth: float, entry_depth: float) -> List[Tuple[str, Rect]]:
    """One candidate from the grammar: [service col][living col][bedroom wing]."""
    t = room_program(bedrooms)
    rooms: List[Tuple[str, Rect]] = []
    front = depth - wet_depth - (PASSAGE if bedrooms > 1 else 0.0)  # bedroom depth
    bed_targets = [t["bedroom"]] * (bedrooms - 1) + [t["master_bedroom"]]
    bed_widths = [max(_SHAPE["bedroom"][0], a / front) for a in bed_targets]
    bed_widths[-1] = max(bed_widths[-1], _SHAPE["master_bedroom"][0])
    service_width = 0.0
    if kitchen_on_facade:
        service_width = max(2.4, (t["kitchen"] + t["utility"]) / depth)
    living_min = 3.4
    wing = sum(bed_widths)
    if width - service_width - wing < living_min:  # squeeze bedrooms to fit
        wing = max(0.0, width - service_width - living_min)
        bed_widths = [w * wing / sum(bed_widths) for w in bed_widths]
    x_living = service_width
    x_wing = width - wing

    # Service column: kitchen on the facade, utility behind it.
    if kitchen_on_facade:
        utility_depth = min(1.6, max(1.0, t["utility"] / service_width))
        rooms += [("utility", (0, 0, service_width, utility_depth)),
                  ("kitchen", (0, utility_depth, service_width, depth))]

    # Living column: back band (entrance + dining or kitchen), front band (living).
    back = []
    if not kitchen_on_facade:
        back.append(("kitchen", t["kitchen"]))
        if bedrooms >= 2:
            back.insert(0, ("utility", t["utility"]))
    if bedrooms >= 3 and kitchen_on_facade:
        back.append(("dining", t["dining"]))
    # The entrance keeps a door-wide strip; the other back-band rooms share the rest.
    entrance_width = max(1.3, t["entrance"] / entry_depth)
    x_entrance = max(x_living, x_wing - entrance_width) if back else x_living
    for (kind, _), (a, b) in zip(back, _split(x_living, x_entrance, [w for _, w in back])):
        rooms.append((kind, (a, 0, b, entry_depth)))
    rooms.append(("entrance", (x_entrance, 0, x_wing, entry_depth)))
    front_band = [("living", t["living"])]
    if bedrooms >= 3 and not kitchen_on_facade:
        front_band.insert(0, ("dining", t["dining"]))
    for (kind, _), (a, b) in zip(front_band, _split(x_living, x_wing, [w for _, w in front_band])):
        rooms.append((kind, (a, entry_depth, b, depth)))

    # Bedroom wing: bedrooms on the facade, passage, then the wet band.
    x = x_wing
    for index, w in enumerate(bed_widths):
        kind = "master_bedroom" if index == len(bed_widths) - 1 else "bedroom"
        rooms.append((kind, (x, depth - front, x + w, depth)))
        x += w
    if bedrooms == 1:
        rooms.append(("bathroom", (x_wing, 0, width, wet_depth)))
        return rooms
    master_x = width - bed_widths[-1] + DOOR + 0.1  # passage reaches the master bedroom
    rooms.append(("master_bathroom", (master_x, 0, width, wet_depth + PASSAGE)))
    rooms.append(("corridor", (x_wing, wet_depth, master_x, wet_depth + PASSAGE)))
    commons = bathroom_count(bedrooms) - 1
    bath_width = max(_SHAPE["bathroom"][0], t["bathroom"] / wet_depth)
    spare = (master_x - x_wing) - commons * bath_width
    cells = [("bathroom", bath_width)] * commons
    if spare >= 0.8:
        cells.append(("storage", spare))
    for (kind, _), (a, b) in zip(cells, _split(x_wing, master_x, [w for _, w in cells])):
        rooms.append((kind, (a, 0, b, wet_depth)))
    return rooms


def _mirror(rooms: List[Tuple[str, Rect]], width: float) -> List[Tuple[str, Rect]]:
    return [(k, (width - r[2], r[1], width - r[0], r[3])) for k, r in rooms]


def solve_apartment(bedrooms: int, width: float, depth: float, variant: int = 0,
                    exterior_sides: Tuple[str, ...] = ()) -> Tuple[List[Tuple[str, Rect]], List, str]:
    """Return (rooms, penalties, name) for the variant-th best distinct arrangement."""
    candidates = []
    wet_options = [1.6, 1.8, 2.0, 2.2, 2.4]
    entry_options = [1.5, 1.8, 2.1, 2.4, 2.7, 3.0, 3.3]
    for on_facade, mirrored, wet, entry in product((True, False), (False, True),
                                                   wet_options, entry_options):
        if entry >= depth - 3.0 or wet + PASSAGE >= depth - 2.7:
            continue
        rooms = build(bedrooms, width, depth, on_facade, wet, entry)
        if mirrored:
            rooms = _mirror(rooms, width)
        penalties = score(rooms, bedrooms, width, depth, exterior_sides)
        name = ("Kitchen on facade" if on_facade else "Compact kitchen by entry") + (
            ", mirrored" if mirrored else "")
        candidates.append((sum(c for c, _ in penalties), name, rooms, penalties))
    candidates.sort(key=lambda item: item[0])
    clean = [item for item in candidates if item[0] < 40] or candidates[:1]  # no hard-rule breaks
    # Distinct arrangements first, then alternative proportions of them.
    seen, picks = set(), []
    for item in clean:
        if item[1] not in seen:
            seen.add(item[1])
            picks.append(item)
    for item in clean:
        if len(picks) >= 3:
            break
        if all(item[2] != pick[2] for pick in picks):
            picks.append((item[0], item[1] + " (alt. proportions)", item[2], item[3]))
    _, name, rooms, penalties = picks[variant % len(picks)]
    return rooms, penalties, name

if __name__ == "__main__":
    # Self-check: exact partitions, and typical flats meet every hard rule.
    for n, area in {1: 40.0, 2: 67.8, 3: 102.2, 4: 148.6}.items():
        depth = min(10.0, max(6.0, area / frontage_needed(n)))
        width = area / depth
        for variant in range(3):
            rooms, penalties, name = solve_apartment(n, width, depth, variant)
            total = sum((r[2] - r[0]) * (r[3] - r[1]) for _, r in rooms)
            assert abs(total - width * depth) < 1e-6, (n, variant, total)
            hard = [p for p in penalties if p[0] >= 40]
            assert not hard, (n, variant, hard)
            print(f"{n}BHK {width:.1f}x{depth:.1f} v{variant} {name}: cost "
                  f"{sum(c for c, _ in penalties):.1f} {penalties}")
