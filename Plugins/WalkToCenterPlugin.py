from PluginManager import plugin, hook

from Helpers.pathfinding import create_pathfinding_state, reset_pathfinding_state, walk_to_goal


@plugin(active=True)
class WalkToCenterPlugin:
    """Walk to realm center (1024, 1024) using shared safe pathfinding helper."""

    CENTER_X = 1024.0
    CENTER_Y = 1024.0
    ARRIVAL_DIST = 3.0
    MAX_ASTAR_NODES = 20000
    RETRY_TICKS = 20
    MIN_TILES_BEFORE_PLAN = 50

    def __init__(self):
        self.is_in_realm = False
        self.walking_to_center = False
        self.state = create_pathfinding_state(
            nowalk_path="Resources/nowalk.txt",
            sink_path="Resources/sink.txt",
            blocked_path="Resources/blocked.txt",
        )

    @hook("mapInfo")
    def onMapInfo(self, client, packet):
        name = getattr(packet, "name", "")
        if "Realm" in name:
            self.is_in_realm = True
            self.walking_to_center = True
            reset_pathfinding_state(self.state, client)
            print(f"[WalkToCenterPlugin] Entered '{name}' - waiting for tile data...")
        else:
            self.is_in_realm = False
            self.walking_to_center = False
            reset_pathfinding_state(self.state, client)

    @hook("update")
    def onUpdate(self, client, packet):
        if not (self.is_in_realm and self.walking_to_center):
            return

        reached = walk_to_goal(
            self.state,
            client,
            packet,
            goal=(self.CENTER_X, self.CENTER_Y),
            arrival_dist=self.ARRIVAL_DIST,
            max_astar_nodes=self.MAX_ASTAR_NODES,
            retry_ticks=self.RETRY_TICKS,
            min_tiles_before_plan=self.MIN_TILES_BEFORE_PLAN,
        )

        if reached:
            self.walking_to_center = False
            print("[WalkToCenterPlugin] Reached center")
