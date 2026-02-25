import re

from PluginManager import plugin, hook
from Networking.PacketHelper import createPacket
from Constants import GameIds
from Constants.StatTypes import StatTypes
from Data.WorldPosData import WorldPosData


PORTAL_AREA_X = 159.0
PORTAL_AREA_Y = 108.0

PORTAL_AREA_ARRIVAL_DIST = 2.0
PORTAL_USE_DIST = 0.25
MAX_VERIFY_TIME_MS = 10_000

REALM_PORTAL_OBJECT_TYPE = 1810


@plugin(active=True)
class EnterRealmPlugin:
    """Automate nexus -> least-crowded realm portal entry.

    Flow:
      1) In nexus, wait until HP is full.
      2) Walk to portal area.
      3) Choose least-crowded visible realm portal.
      4) Walk to portal and send USEPORTAL.
      5) Verify transition to realm, else retry.
    """

    def __init__(self):
        self.foundPortals = {}
        self.realmPortal = None

        self.walkingToArea = False
        self.walkingToPortal = False
        self.sequenceStarted = False
        self.verifyInRealm = False
        self.verifyStartTime = 0

        self.portalAreaPos = WorldPosData(PORTAL_AREA_X, PORTAL_AREA_Y)

        print("[EnterRealmPlugin] Loaded")

    def _hpIsFull(self, client):
        if client.playerData.maxHp <= 0:
            return False
        return client.playerData.hp >= client.playerData.maxHp

    def _parsePlayerCount(self, obj):
        for stat in obj.status.stats or []:
            if stat.statType != StatTypes.NAMESTAT:
                continue
            if not stat.isStringStat():
                continue
            match = re.search(r"\((\d+)/\d+\)", stat.strStatValue)
            if match:
                return int(match.group(1))
        return None

    def _selectLeastCrowdedPortal(self):
        candidates = [p for p in self.foundPortals.values() if self._parsePlayerCount(p) is not None]
        if len(candidates) == 0:
            return None
        return min(candidates, key=self._parsePlayerCount)

    def _reset(self):
        self.foundPortals = {}
        self.realmPortal = None

        self.walkingToArea = False
        self.walkingToPortal = False
        self.sequenceStarted = False
        self.verifyInRealm = False
        self.verifyStartTime = 0

    def _startSequence(self):
        self._reset()
        self.walkingToArea = True
        self.sequenceStarted = True

    @hook("mapInfo")
    def onMapInfo(self, client, packet):
        self._reset()

        if client.gameId == GameIds.nexus:
            self._startSequence()
            print("[EnterRealmPlugin] In nexus, waiting for full HP...")
            return

        if client.gameId == GameIds.randomRealm or "Realm" in packet.name:
            print(f"[EnterRealmPlugin] Entered realm: {packet.name}")

    @hook("update")
    def onUpdate(self, client, packet):
        for droppedId in packet.drops:
            self.foundPortals.pop(droppedId, None)

        for obj in packet.newObjs:
            if obj.objectType == REALM_PORTAL_OBJECT_TYPE:
                self.foundPortals[obj.status.objectId] = obj

        if not self.sequenceStarted:
            return

        if client.pos is None:
            return

        if not self._hpIsFull(client):
            return

        if self.walkingToArea:
            if client.pos.dist(self.portalAreaPos) > PORTAL_AREA_ARRIVAL_DIST:
                client.nextPos = [self.portalAreaPos]
                return

            self.walkingToArea = False
            selected = self._selectLeastCrowdedPortal()
            if selected is None:
                self.walkingToArea = True
                return

            self.realmPortal = selected
            self.walkingToPortal = True
            return

        if self.walkingToPortal and self.realmPortal is not None:
            portalPos = self.realmPortal.status.pos
            if client.pos.dist(portalPos) > PORTAL_USE_DIST:
                client.nextPos = [portalPos]
                return

            usePortal = createPacket("USEPORTAL")
            usePortal.objectId = self.realmPortal.status.objectId
            client.send(usePortal)

            self.walkingToPortal = False
            self.realmPortal = None
            self.verifyInRealm = True
            self.verifyStartTime = client.getTime()
            return

        if self.verifyInRealm:
            if client.gameId == GameIds.randomRealm:
                print("[EnterRealmPlugin] Verified in realm")
                self._reset()
                return

            if client.getTime() - self.verifyStartTime > MAX_VERIFY_TIME_MS:
                print("[EnterRealmPlugin] Portal entry timeout, retrying")
                self._startSequence()
