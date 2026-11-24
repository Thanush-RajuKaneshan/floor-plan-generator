"""Geometry-based checks for early floor-plan concepts."""

from collections import deque
from typing import Dict, List, Optional

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from apartment_solver import ACCESS_FROM

_LIGHT_DONORS = {"dining": ("living", 2.4), "kitchen": ("utility", 1.2)}
_BATH_TYPES = {"bathroom", "master_bathroom"}
# A bathroom gets one door, from the first of these it touches.
_BATH_DOOR_PRIORITY = ("master_bedroom", "bedroom", "corridor", "dining", "entrance", "living")


def _door_allowed(first: str, second: str) -> bool:
    return first in ACCESS_FROM.get(second, ()) or second in ACCESS_FROM.get(first, ())


_HABITABLE_ROOM_TYPES = {"living", "dining", "kitchen", "bedroom", "master_bedroom"}
_DOOR_WIDTHS = {
    "entrance": 0.9,
    "bathroom": 0.7,
    "master_bathroom": 0.7,
}


def _shared_segment(first: Polygon, second: Polygon) -> Optional[LineString]:
    # Tolerance: rotated plans leave float noise between walls that should coincide.
    shared = first.boundary.intersection(second.buffer(1e-6))
    if shared.geom_type == "LineString" and shared.length > 0:
        return shared
    if shared.geom_type == "MultiLineString":
        segments = [segment for segment in shared.geoms if segment.length > 0]
        return max(segments, key=lambda segment: segment.length) if segments else None
    return None


def _opening_segment(shared: LineString, width: float) -> List[List[float]]:
    start_distance = max(0.0, (shared.length - width) / 2)
    end_distance = min(shared.length, start_distance + width)
    start = shared.interpolate(start_distance)
    end = shared.interpolate(end_distance)
    return [[start.x, start.y], [end.x, end.y]]


def build_geometry_review(layout: Dict) -> Dict:
    """Build door candidates and report basic spatial/access relationships."""

    floorplate_parts = [
        Polygon(apartment["zone_boundary"])
        for apartment in layout.get("apartments", [])
    ]
    floorplate_parts.extend(
        Polygon(element["polygon"])
        for element in layout.get("circulation_elements", [])
        if element.get("polygon")
    )
    floorplate_boundary = unary_union(floorplate_parts).boundary
    connections: List[Dict] = []
    apartment_reports = []
    all_apartment_rooms_connected = True
    all_entries_reach_common_corridor = True
    all_habitable_rooms_have_facade = True

    common_corridor = next(
        (
            element for element in layout.get("circulation_elements", [])
            if element.get("type") == "corridor"
        ),
        None,
    )
    central_lobby = next(
        (
            element for element in layout.get("circulation_elements", [])
            if element.get("type") == "central_lobby"
        ),
        None,
    )
    core_connections_valid = bool(common_corridor and central_lobby)
    if core_connections_valid:
        corridor_polygon = Polygon(common_corridor["polygon"])
        lobby_polygon = Polygon(central_lobby["polygon"])
        core_connections_valid = (
            _shared_segment(corridor_polygon, lobby_polygon) is not None
        )

    for apartment in layout.get("apartments", []):
        rooms = apartment.get("rooms", [])
        room_geometries = {
            room["room_id"]: Polygon(room["polygon"])
            for room in rooms
        }
        graph = {room_id: set() for room_id in room_geometries}

        candidates = []
        for index, first in enumerate(rooms):
            first_id = first["room_id"]
            for second in rooms[index + 1:]:
                second_id = second["room_id"]
                if not _door_allowed(first["type"], second["type"]):
                    continue
                shared = _shared_segment(
                    room_geometries[first_id],
                    room_geometries[second_id],
                )
                if shared is None or shared.length < 0.6:
                    continue

                requested_width = max(
                    _DOOR_WIDTHS.get(first["type"], 0.8),
                    _DOOR_WIDTHS.get(second["type"], 0.8),
                )
                if shared.length < requested_width + 0.1:
                    continue

                candidates.append((first, second, shared, requested_width))

        bath_door = {}
        for first, second, _, _ in candidates:
            for bath, other in ((first, second), (second, first)):
                if bath["type"] in _BATH_TYPES and other["type"] in _BATH_DOOR_PRIORITY:
                    rank = _BATH_DOOR_PRIORITY.index(other["type"])
                    current = bath_door.get(bath["room_id"])
                    if current is None or rank < current[0]:
                        bath_door[bath["room_id"]] = (rank, other["room_id"])
        for first, second, shared, requested_width in candidates:
            first_id, second_id = first["room_id"], second["room_id"]
            if any(
                room["type"] in _BATH_TYPES and bath_door[room["room_id"]][1] != other_id
                for room, other_id in ((first, second_id), (second, first_id))
            ):
                continue
            graph[first_id].add(second_id)
            graph[second_id].add(first_id)
            connections.append({
                "apartment_number": apartment["apartment_number"],
                "from_room": first_id,
                "to_room": second_id,
                "clear_width_m": requested_width,
                "segment": _opening_segment(shared, requested_width),
            })

        entrance = next(
            (room for room in rooms if room.get("type") == "entrance"),
            None,
        )
        reachable = set()
        if entrance:
            queue = deque([entrance["room_id"]])
            reachable.add(entrance["room_id"])
            while queue:
                for neighbor in graph[queue.popleft()]:
                    if neighbor not in reachable:
                        reachable.add(neighbor)
                        queue.append(neighbor)

        required_rooms = {
            room["room_id"] for room in rooms
            if room.get("type") in _HABITABLE_ROOM_TYPES
        }
        unreachable = sorted(required_rooms - reachable)
        if unreachable:
            all_apartment_rooms_connected = False

        entry_reaches_common = bool(
            entrance
            and common_corridor
            and _shared_segment(
                room_geometries[entrance["room_id"]],
                Polygon(common_corridor["polygon"]),
            )
        )
        if not entry_reaches_common:
            all_entries_reach_common_corridor = False

        def touches_facade(room_id):
            return room_geometries[room_id].boundary.intersection(
                floorplate_boundary.buffer(1e-6)
            ).length >= 0.5

        facade_rooms = []
        for room in rooms:
            if room.get("type") not in _HABITABLE_ROOM_TYPES:
                continue
            # Borrowed light: dining open to living, kitchen through an outside utility.
            donor, opening = _LIGHT_DONORS.get(room["type"], (None, 0))
            has_facade_contact = touches_facade(room["room_id"]) or any(
                other["type"] == donor and touches_facade(other["room_id"])
                and (_shared_segment(room_geometries[room["room_id"]],
                                     room_geometries[other["room_id"]]) or LineString()).length >= opening
                for other in rooms
            )
            facade_rooms.append({
                "room_id": room["room_id"],
                "room_type": room["type"],
                "has_potential_facade": has_facade_contact,
            })
            if not has_facade_contact:
                all_habitable_rooms_have_facade = False

        apartment_reports.append({
            "apartment_number": apartment["apartment_number"],
            "entrance_found": entrance is not None,
            "entrance_reaches_common_corridor": entry_reaches_common,
            "all_habitable_rooms_reachable": not unreachable,
            "unreachable_rooms": unreachable,
            "potential_facade_contacts": facade_rooms,
        })

    checks = [
        {
            "id": "room_access",
            "status": "pass" if all_apartment_rooms_connected else "fail",
            "summary": (
                "Every modeled habitable room is connected to its apartment entrance."
                if all_apartment_rooms_connected
                else "At least one modeled habitable room has no geometric route to its entrance."
            ),
        },
        {
            "id": "common_access",
            "status": "pass" if (
                all_entries_reach_common_corridor and core_connections_valid
            ) else "fail",
            "summary": (
                "Apartment entrances touch the common corridor, which touches the lobby."
                if all_entries_reach_common_corridor and core_connections_valid
                else "The common corridor, apartment entrances, or lobby do not form one connected path."
            ),
        },
        {
            "id": "facade_potential",
            "status": "pass" if all_habitable_rooms_have_facade else "warning",
            "summary": (
                "All modeled habitable rooms touch the envelope and have potential for a facade opening."
                if all_habitable_rooms_have_facade
                else "Some habitable rooms do not touch the envelope; daylight and ventilation need review."
            ),
        },
        {
            "id": "stair_design",
            "status": "warning",
            "summary": (
                "The staircase is still a schematic footprint; risers, treads, landings, "
                "headroom, doors, and fire egress are not designed or code-checked."
            ),
        },
        {
            "id": "openings",
            "status": "warning",
            "summary": (
                "Door candidates indicate room-to-room adjacency only. Door leaves, "
                "swings, wall thicknesses, and window sizes are not modeled."
            ),
        },
    ]

    return {
        "review_type": "geometry_and_adjacency",
        "is_concept_only": True,
        "checks": checks,
        "apartments": apartment_reports,
        "door_candidates": connections,
        "door_candidate_count": len(connections),
        "limitations": [
            "These checks describe polygon adjacency, not construction-ready openings.",
            "No regulatory compliance, daylight, ventilation, structure, fire safety, or accessibility approval is implied.",
        ],
    }


def build_local_ai_input(layout: Dict) -> Dict:
    """Reduce a plan to bounded, non-image facts for an optional local reviewer."""

    review = layout.get("architectural_review", {})
    info = layout.get("building_info", layout)  # saved JSON nests the metrics
    return {
        "design_variant": layout.get("metadata", layout).get("design_variant_name"),
        "plot_area_sqm": round(float(info.get("plot_area", 0)), 1),
        "floor_area_sqm": round(float(info.get("floor_area", 0)), 1),
        "ground_coverage_percent": round(
            float(info.get("ground_coverage_utilized", 0)) * 100, 1
        ),
        "fsi_used": round(float(info.get("fsi_utilized", 0)), 2),
        "floors": int(info.get("floors", 1)),
        "apartments": [
            {
                "number": apartment.get("apartment_number"),
                "bedrooms": apartment.get("bedrooms"),
                "area_sqm": round(float(apartment.get("total_area", 0)), 1),
                "arrangement": apartment.get("arrangement"),
                "rooms": [
                    f"{room.get('type')} {float(room.get('area', 0)):.1f} m2"
                    for room in apartment.get("rooms", [])
                ],
                "design_issues": apartment.get("design_issues", []),
            }
            for apartment in layout.get("apartments", [])
        ],
        "geometry_checks": [
            {"id": check["id"], "status": check["status"], "summary": check["summary"]}
            for check in review.get("checks", [])
        ],
        "apartment_findings": [
            {
                "apartment_number": apartment["apartment_number"],
                "unreachable_rooms": apartment["unreachable_rooms"],
                "rooms_without_facade_potential": [
                    room["room_type"]
                    for room in apartment["potential_facade_contacts"]
                    if not room["has_potential_facade"]
                ],
            }
            for apartment in review.get("apartments", [])
        ],
        "door_candidate_count": review.get("door_candidate_count", 0),
    }
