from PluginManager import plugin, hook
import heapq
import math

from Data.WorldPosData import WorldPosData


class Node:
    """A* search node."""
    __slots__ = ('x', 'y', 'g', 'h', 'f', 'parent')

    def __init__(self, x, y, g=0.0, h=0.0, parent=None):
        self.x = x
        self.y = y
        self.g = g
        self.h = h
        self.f = g + h
        self.parent = parent

    def __lt__(self, other):
        return self.f < other.f


@plugin(active=True)
class WalkToCenterPlugin:
    """Walk to realm center (1024, 1024) using A* and live map/object data."""

    CENTER_X = 1024.0
    CENTER_Y = 1024.0
    ARRIVAL_DIST = 3.0
    MAX_ASTAR_NODES = 20000
    RETRY_TICKS = 20
    MIN_TILES_BEFORE_PLAN = 50

    # All files are expected in Resources/ next to equip.xml.
    NOWALK_PATH = "Resources/nowalk.txt"
    SINK_PATH = "Resources/sink.txt"
    BLOCKED_PATH = "Resources/blocked.txt"

    def __init__(self):
        self.is_in_realm = False
        self.walking_to_center = False

        self.tile_map = {}      # (int_x, int_y) -> tile_type int
        self.obj_map = {}       # (int_x, int_y) -> set(objectIds)
        self._oid_to_pos = {}   # objectId -> (int_x, int_y)

        self._committed_path = []
        self._is_partial_path = False
        self._retry_countdown = 0
        self._goal = (int(self.CENTER_X), int(self.CENTER_Y))

        self.nowalk_tiles = self._load_tile_set(self.NOWALK_PATH)
        self.sink_tiles = self._load_tile_set(self.SINK_PATH)
        self.blocked_types = self._load_blocked_objects(self.BLOCKED_PATH)

        print("[WalkToCenterPlugin] Loaded | "
              f"nowalk={len(self.nowalk_tiles)} | "
              f"sink={len(self.sink_tiles)} | "
              f"blocking_objects={len(self.blocked_types)}")

    @staticmethod
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
            print(f"[WalkToCenterPlugin] WARNING: not found - {filepath}")
        except OSError as exc:
            print(f"[WalkToCenterPlugin] ERROR reading {filepath}: {exc}")
        return result

    @staticmethod
    def _load_blocked_objects(filepath):
        """Load objectType ids whose properties include OccupySquare."""
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
            print(f"[WalkToCenterPlugin] WARNING: not found - {filepath}")
        except OSError as exc:
            print(f"[WalkToCenterPlugin] ERROR reading {filepath}: {exc}")
        return result

    def _is_walkable(self, x, y):
        tile_type = self.tile_map.get((x, y))
        if tile_type is None or tile_type < 0:
            return False
        if tile_type in self.nowalk_tiles or tile_type in self.sink_tiles:
            return False
        if self.obj_map.get((x, y)):
            return False
        return True

    @staticmethod
    def _heuristic(x1, y1, x2, y2):
        dx, dy = abs(x1 - x2), abs(y1 - y2)
        return max(dx, dy) + (math.sqrt(2) - 1.0) * min(dx, dy)

    def _neighbors(self, x, y):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            nx, ny = x + dx, y + dy
            if dx != 0 and dy != 0:
                if not (self._is_walkable(x + dx, y) and self._is_walkable(x, y + dy)):
                    continue
            if self._is_walkable(nx, ny):
                yield nx, ny, (1.4142135 if (dx != 0 and dy != 0) else 1.0)

    @staticmethod
    def _rebuild(node):
        path = []
        cur = node
        while cur:
            path.append((cur.x, cur.y))
            cur = cur.parent
        path.reverse()
        return path

    def _astar(self, sx, sy, gx, gy):
        start = Node(sx, sy, g=0.0, h=self._heuristic(sx, sy, gx, gy))
        open_heap = [(start.f, start)]
        best_g = {(sx, sy): 0.0}
        closed = set()
        best_node = start

        iters = 0
        while open_heap and iters < self.MAX_ASTAR_NODES:
            iters += 1
            _, current = heapq.heappop(open_heap)
            pos = (current.x, current.y)
            if pos in closed:
                continue
            closed.add(pos)

            if current.h < best_node.h:
                best_node = current

            if pos == (gx, gy):
                return self._rebuild(current), True

            for nx, ny, cost in self._neighbors(current.x, current.y):
                npos = (nx, ny)
                if npos in closed:
                    continue
                ng = current.g + cost
                if ng < best_g.get(npos, float("inf")):
                    best_g[npos] = ng
                    nb = Node(nx, ny, g=ng,
                              h=self._heuristic(nx, ny, gx, gy),
                              parent=current)
                    heapq.heappush(open_heap, (nb.f, nb))

        if best_node.x == sx and best_node.y == sy:
            return None, False
        return self._rebuild(best_node), False

    @staticmethod
    def _make_pos(x, y):
        p = WorldPosData()
        p.x = x
        p.y = y
        return p

    def _path_to_worldpos(self, path):
        return [self._make_pos(tx + 0.5, ty + 0.5) for tx, ty in path[1:]]

    def _overlaps_remaining(self, coords):
        remaining = set(self._committed_path[1:])
        return bool(remaining & coords)

    def _commit_path(self, client, path, reached):
        self._committed_path = path
        self._is_partial_path = not reached
        waypoints = self._path_to_worldpos(path)
        client.nextPos = waypoints

        end = path[-1]
        status = "full" if reached else f"frontier->({end[0]},{end[1]})"
        print(f"[WalkToCenterPlugin] Path committed: {len(waypoints)} waypoints "
              f"[{status}] | tiles={len(self.tile_map)}")

    def _cancel_path(self, client):
        self._committed_path = []
        self._is_partial_path = False
        client.nextPos = []

    @hook("mapInfo")
    def onMapInfo(self, client, packet):
        name = getattr(packet, "name", "")
        if "Realm" in name:
            self.is_in_realm = True
            self.walking_to_center = True
            self._retry_countdown = 0
            self.tile_map.clear()
            self.obj_map.clear()
            self._oid_to_pos.clear()
            self._cancel_path(client)
            print(f"[WalkToCenterPlugin] Entered '{name}' - waiting for tile data...")
        else:
            self.is_in_realm = False
            self.walking_to_center = False
            self.tile_map.clear()
            self.obj_map.clear()
            self._oid_to_pos.clear()
            self._cancel_path(client)

    @hook("update")
    def onUpdate(self, client, packet):
        needs_replan = False

        changed_tiles = set()
        for tile in getattr(packet, "tiles", []):
            tx = getattr(tile, "x", None)
            ty = getattr(tile, "y", None)
            tt = getattr(tile, "type", None)
            if tx is None or ty is None or tt is None:
                continue
            key = (int(tx), int(ty))
            old = self.tile_map.get(key)
            if old == tt:
                continue
            self.tile_map[key] = tt

            def _tile_walkable(t):
                return (t is not None and t >= 0
                        and t not in self.nowalk_tiles
                        and t not in self.sink_tiles)

            if _tile_walkable(old) != _tile_walkable(tt):
                changed_tiles.add(key)

        if changed_tiles and self._overlaps_remaining(changed_tiles):
            print("[WalkToCenterPlugin] Tile walkability changed on path - replanning")
            needs_replan = True

        new_obj_tiles = set()
        for obj in getattr(packet, "newObjs", []):
            if obj.objectType not in self.blocked_types:
                continue
            ox = int(obj.status.pos.x)
            oy = int(obj.status.pos.y)
            key = (ox, oy)
            oid = obj.status.objectId

            if key not in self.obj_map:
                self.obj_map[key] = set()
            self.obj_map[key].add(oid)
            self._oid_to_pos[oid] = key
            new_obj_tiles.add(key)

        if new_obj_tiles and self._overlaps_remaining(new_obj_tiles):
            print("[WalkToCenterPlugin] Blocking object on path - replanning")
            needs_replan = True

        for oid in getattr(packet, "drops", []):
            key = self._oid_to_pos.pop(oid, None)
            if key is None:
                continue
            oids = self.obj_map.get(key)
            if oids:
                oids.discard(oid)
                if len(oids) == 0:
                    del self.obj_map[key]

        if not (self.is_in_realm and self.walking_to_center):
            return

        pos = getattr(client, "pos", None)
        if pos is None:
            return

        dist = math.hypot(pos.x - self.CENTER_X, pos.y - self.CENTER_Y)
        if dist < self.ARRIVAL_DIST:
            self.walking_to_center = False
            self._cancel_path(client)
            print(f"[WalkToCenterPlugin] Reached center (dist={dist:.2f})")
            return

        if len(self.tile_map) < self.MIN_TILES_BEFORE_PLAN:
            return

        if self._retry_countdown > 0:
            self._retry_countdown -= 1
            return

        queue_empty = len(client.nextPos) == 0
        frontier_done = self._is_partial_path and queue_empty

        if needs_replan or queue_empty or frontier_done:
            self._plan(client, pos)

    def _plan(self, client, pos):
        cx, cy = int(pos.x), int(pos.y)
        gx, gy = self._goal

        path, reached = self._astar(cx, cy, gx, gy)
        if not path or len(path) < 2:
            print("[WalkToCenterPlugin] A* no usable path "
                  f"(tiles={len(self.tile_map)}, blocked_tiles={len(self.obj_map)}) "
                  f"- retrying in {self.RETRY_TICKS} ticks")
            self._cancel_path(client)
            self._retry_countdown = self.RETRY_TICKS
            return

        self._commit_path(client, path, reached)
