from PluginManager import plugin, hook
from Networking.PacketHelper import createPacket
from Constants import GameIds
from Data.WorldPosData import WorldPosData
import re
import Plugins.InformationStreamPlugin as isp
import time

# ── config ────────────────────────────────────────────────────────────────────
PORTAL_AREA_X = 159.0   # nexus coords to walk toward before picking a portal
PORTAL_AREA_Y = 108.0

PORTAL_AREA_ARRIVAL_DIST = 2.00    # world units – "close enough" to portal area
PORTAL_USE_DIST = 0.25             # world units – close enough to send USEPORTAL
MAX_VERIFY_TIME = 10.0             # seconds to wait for realm entry before retrying
# ─────────────────────────────────────────────────────────────────────────────


@plugin(active=True)
class EnterRealmPlugin:
    """
    Full automated nexus → realm entry sequence:

      1. On arriving in the nexus, wait until HP is 100%.
      2. Walk to the portal area (PORTAL_AREA_X / Y).
      3. Select the least-crowded realm portal visible.
      4. Walk to that portal and send USEPORTAL.
      5. Verify the map transition. If it doesn't happen within
         MAX_VERIFY_TIME seconds, reset and retry from step 1.
    """

    def __init__(self):
        self.found_portals = []
        self.realm_portal = None

        self._walking_to_area = False
        self._walking_to_portal = False
        self._sequence_started = False
        self._verify_in_realm = False
        self._verify_start_time = 0.0

        self._portal_area_pos = self._make_pos(PORTAL_AREA_X, PORTAL_AREA_Y)

        print("[EnterRealmPlugin] Loaded – will enter the least-crowded realm once HP is 100%")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_pos(x, y):
        p = WorldPosData()
        p.x = x
        p.y = y
        return p

    @staticmethod
    def _hp_is_full():
        max_hp = isp.max_hp
        cur_hp = isp.current_hp
        if max_hp <= 0 or cur_hp < 0:
            return False
        return cur_hp >= max_hp

    @staticmethod
    def _parse_player_count(portal):
        """Return current player count from a portal's name stat, or None."""
        for stat in (portal.status.stats or []):
            if stat.statType == 31 and stat.isStringStat():
                m = re.search(r'\((\d+)/\d+\)', stat.strStatValue)
                if m:
                    return int(m.group(1))
        return None

    def _select_least_crowded_portal(self):
        if not self.found_portals:
            return None
        return min(
            (p for p in self.found_portals if self._parse_player_count(p) is not None),
            key=self._parse_player_count,
            default=None,
        )

    def _reset(self):
        self.found_portals = []
        self.realm_portal = None
        self._walking_to_area = False
        self._walking_to_portal = False
        self._sequence_started = False
        self._verify_in_realm = False
        self._verify_start_time = 0.0

    def _start_sequence(self):
        """Arm the entry sequence from phase 1."""
        self._reset()
        self._walking_to_area = True
        self._sequence_started = True

    # ── hooks ─────────────────────────────────────────────────────────────────

    @hook("mapInfo")
    def on_map_info(self, client, packet):
        self._reset()
        game_id = getattr(client, 'gameId', None)
        map_name = getattr(packet, 'name', '')

        if game_id == GameIds.nexus:
            self._start_sequence()
            print("[EnterRealmPlugin] In nexus – waiting for 100% HP before moving…")
        elif 'Realm' in map_name:
            # Successful entry confirmed by map transition
            print(f"[EnterRealmPlugin] Entered realm: {map_name}")

    @hook("update")
    def on_update(self, client, packet):
        # Collect realm portals from every update packet
        for obj in packet.newObjs:
            if obj.objectType == 1810:
                self.found_portals.append(obj)
                count = self._parse_player_count(obj)
                print(f"[EnterRealmPlugin] Portal found | id={obj.status.objectId} "
                      f"pos=({obj.status.pos.x:.1f},{obj.status.pos.y:.1f}) "
                      f"players={count}")

        # Remove dropped portal objects from local list
        if packet.drops:
            self.found_portals = [p for p in self.found_portals if p.status.objectId not in packet.drops]

        if not self._sequence_started:
            return

        pos = getattr(client, 'pos', None)
        if pos is None:
            return

        # ── gate: wait for full HP ───────────────────────────────────────────
        if not self._hp_is_full():
            return

        # ── phase 1: walk to portal area ─────────────────────────────────────
        if self._walking_to_area:
            if pos.dist(self._portal_area_pos) > PORTAL_AREA_ARRIVAL_DIST:
                client.nextPos = [self._portal_area_pos]
            else:
                self._walking_to_area = False
                print("[EnterRealmPlugin] Reached portal area – selecting realm…")
                portal = self._select_least_crowded_portal()
                if portal:
                    self.realm_portal = portal
                    self._walking_to_portal = True
                    count = self._parse_player_count(portal)
                    print(f"[EnterRealmPlugin] Selected portal id={portal.status.objectId} ({count} players)")
                else:
                    print("[EnterRealmPlugin] No valid portals yet – retrying when more arrive")
                    self._walking_to_area = True   # stay in phase 1 until portals show up
            return

        # ── phase 2: walk to portal and use it ───────────────────────────────
        if self._walking_to_portal and self.realm_portal:
            portal_pos = self.realm_portal.status.pos
            if pos.dist(portal_pos) > PORTAL_USE_DIST:
                client.nextPos = [portal_pos]
            else:
                time.sleep(1)
                pkt = createPacket("USEPORTAL")
                pkt.objectId = self.realm_portal.status.objectId
                client.send(pkt)
                print(f"[EnterRealmPlugin] Sent USEPORTAL id={self.realm_portal.status.objectId}")
                self._walking_to_portal = False
                self.realm_portal = None
                self._verify_in_realm = True
                self._verify_start_time = client.getTime() / 1000.0
            return

        # ── phase 3: verify transition, retry on timeout ──────────────────────
        if self._verify_in_realm:
            elapsed = (client.getTime() / 1000.0) - self._verify_start_time

            if getattr(client, 'gameId', None) == GameIds.randomRealm:
                print("[EnterRealmPlugin] Verified in realm")
                self._reset()
                return

            if elapsed > MAX_VERIFY_TIME:
                print(f"[EnterRealmPlugin] Entry timeout after {elapsed:.1f}s – retrying…")
                self._start_sequence()
