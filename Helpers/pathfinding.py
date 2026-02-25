import heapq
import math
from dataclasses import dataclass, field

from Data.WorldPosData import WorldPosData


@dataclass
class PathfindingState:
    tile_map: dict = field(default_factory=dict)
    obj_map: dict = field(default_factory=dict)
    oid_to_pos: dict = field(default_factory=dict)
    committed_path: list = field(default_factory=list)
    is_partial_path: bool = False
    retry_countdown: int = 0
    nowalk_tiles: set = field(default_factory=set)
    sink_tiles: set = field(default_factory=set)
    blocked_types: set = field(default_factory=set)


class Node:
    __slots__ = ("x", "y", "g", "h", "f", "parent")

    def __init__(self, x, y, g=0.0, h=0.0, parent=None):
        self.x = x
        self.y = y
        self.g = g
        self.h = h
        self.f = g + h
        self.parent = parent

    def __lt__(self, other):
        return self.f < other.f


def _load_tile_set(filepath):
    result = set()
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw in fh:
                parts = raw.strip().split("\t")
                if len(parts) == 0 or parts[0] == "":
                    continue
                try:
                    result.add(int(parts[0]))
                except ValueError:
                    pass
    except FileNotFoundError:
        print(f"[Pathfinding] WARNING: not found - {filepath}")
    except OSError as exc:
        print(f"[Pathfinding] ERROR reading {filepath}: {exc}")
    return result


def _load_blocked_objects(filepath):
    result = set()
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw in fh:
                parts = raw.strip().split("\t")
                if len(parts) < 4:
                    continue
                if "OccupySquare" not in parts[3]:
                    continue
                try:
                    result.add(int(parts[0]))
                except ValueError:
                    pass
    except FileNotFoundError:
        print(f"[Pathfinding] WARNING: not found - {filepath}")
    except OSError as exc:
        print(f"[Pathfinding] ERROR reading {filepath}: {exc}")
    return result


def create_pathfinding_state(
    nowalk_path="Resources/nowalk.txt",
    sink_path="Resources/sink.txt",
    blocked_path="Resources/blocked.txt",
):
    state = PathfindingState()
    state.nowalk_tiles = _load_tile_set(nowalk_path)
    state.sink_tiles = _load_tile_set(sink_path)
    state.blocked_types = _load_blocked_objects(blocked_path)
    print(
        "[Pathfinding] Loaded | "
        f"nowalk={len(state.nowalk_tiles)} | "
        f"sink={len(state.sink_tiles)} | "
        f"blocking_objects={len(state.blocked_types)}"
    )
    return state


def reset_pathfinding_state(state, client):
    state.tile_map.clear()
    state.obj_map.clear()
    state.oid_to_pos.clear()
    state.committed_path = []
    state.is_partial_path = False
    state.retry_countdown = 0
    client.nextPos = []


def _is_walkable(state, x, y):
    tile_type = state.tile_map.get((x, y))
    if tile_type is None or tile_type < 0:
        return False
    if tile_type in state.nowalk_tiles or tile_type in state.sink_tiles:
        return False
    if state.obj_map.get((x, y)):
        return False
    return True


def _heuristic(x1, y1, x2, y2):
    dx, dy = abs(x1 - x2), abs(y1 - y2)
    return max(dx, dy) + (math.sqrt(2) - 1.0) * min(dx, dy)


def _neighbors(state, x, y):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        nx, ny = x + dx, y + dy
        if dx != 0 and dy != 0:
            if not (_is_walkable(state, x + dx, y) and _is_walkable(state, x, y + dy)):
                continue
        if _is_walkable(state, nx, ny):
            yield nx, ny, (1.4142135 if (dx != 0 and dy != 0) else 1.0)


def _rebuild(node):
    path = []
    cur = node
    while cur:
        path.append((cur.x, cur.y))
        cur = cur.parent
    path.reverse()
    return path


def _astar(state, sx, sy, gx, gy, max_nodes):
    start = Node(sx, sy, g=0.0, h=_heuristic(sx, sy, gx, gy))
    open_heap = [(start.f, start)]
    best_g = {(sx, sy): 0.0}
    closed = set()
    best_node = start

    iters = 0
    while open_heap and iters < max_nodes:
        iters += 1
        _, current = heapq.heappop(open_heap)
        pos = (current.x, current.y)
        if pos in closed:
            continue
        closed.add(pos)

        if current.h < best_node.h:
            best_node = current

        if pos == (gx, gy):
            return _rebuild(current), True

        for nx, ny, cost in _neighbors(state, current.x, current.y):
            npos = (nx, ny)
            if npos in closed:
                continue
            ng = current.g + cost
            if ng < best_g.get(npos, float("inf")):
                best_g[npos] = ng
                nb = Node(nx, ny, g=ng, h=_heuristic(nx, ny, gx, gy), parent=current)
                heapq.heappush(open_heap, (nb.f, nb))

    if best_node.x == sx and best_node.y == sy:
        return None, False
    return _rebuild(best_node), False


def _overlaps_remaining(state, coords):
    remaining = set(state.committed_path[1:])
    return bool(remaining & coords)


def _path_to_worldpos(path):
    return [WorldPosData(tx + 0.5, ty + 0.5) for tx, ty in path[1:]]


def walk_to_goal(
    state,
    client,
    packet,
    goal,
    arrival_dist=3.0,
    max_astar_nodes=20000,
    retry_ticks=20,
    min_tiles_before_plan=50,
):
    """Ingest update packet and safely path toward (goal_x, goal_y)."""
    goal_x, goal_y = goal
    needs_replan = False

    changed_tiles = set()
    for tile in getattr(packet, "tiles", []):
        tx = getattr(tile, "x", None)
        ty = getattr(tile, "y", None)
        tt = getattr(tile, "type", None)
        if tx is None or ty is None or tt is None:
            continue

        key = (int(tx), int(ty))
        old = state.tile_map.get(key)
        if old == tt:
            continue
        state.tile_map[key] = tt

        def _tile_walkable(t):
            return (t is not None and t >= 0 and t not in state.nowalk_tiles and t not in state.sink_tiles)

        if _tile_walkable(old) != _tile_walkable(tt):
            changed_tiles.add(key)

    if changed_tiles and _overlaps_remaining(state, changed_tiles):
        needs_replan = True

    new_obj_tiles = set()
    for obj in getattr(packet, "newObjs", []):
        if obj.objectType not in state.blocked_types:
            continue

        key = (int(obj.status.pos.x), int(obj.status.pos.y))
        oid = obj.status.objectId
        if key not in state.obj_map:
            state.obj_map[key] = set()
        state.obj_map[key].add(oid)
        state.oid_to_pos[oid] = key
        new_obj_tiles.add(key)

    if new_obj_tiles and _overlaps_remaining(state, new_obj_tiles):
        needs_replan = True

    for oid in getattr(packet, "drops", []):
        key = state.oid_to_pos.pop(oid, None)
        if key is None:
            continue
        oids = state.obj_map.get(key)
        if oids:
            oids.discard(oid)
            if len(oids) == 0:
                del state.obj_map[key]

    pos = getattr(client, "pos", None)
    if pos is None:
        return False

    if math.hypot(pos.x - goal_x, pos.y - goal_y) < arrival_dist:
        client.nextPos = []
        state.committed_path = []
        state.is_partial_path = False
        return True

    if len(state.tile_map) < min_tiles_before_plan:
        return False

    if state.retry_countdown > 0:
        state.retry_countdown -= 1
        return False

    queue_empty = len(client.nextPos) == 0
    frontier_done = state.is_partial_path and queue_empty
    if not (needs_replan or queue_empty or frontier_done):
        return False

    cx, cy = int(pos.x), int(pos.y)
    gx, gy = int(goal_x), int(goal_y)
    path, reached = _astar(state, cx, cy, gx, gy, max_astar_nodes)
    if not path or len(path) < 2:
        client.nextPos = []
        state.committed_path = []
        state.is_partial_path = False
        state.retry_countdown = retry_ticks
        return False

    state.committed_path = path
    state.is_partial_path = not reached
    client.nextPos = _path_to_worldpos(path)
    return False
