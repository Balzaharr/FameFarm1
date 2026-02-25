from dataclasses import dataclass
from enum import Enum, auto

from Constants import GameIds
from Data.WorldPosData import WorldPosData
from PluginManager import plugin, hook


# ── config ────────────────────────────────────────────────────────────────────
NEXUS_HP_THRESHOLD = 0.33
RESUME_HP_THRESHOLD = 1.00
NEXUS_COOLDOWN_TICKS = 10

HEAL_SPOT_X = 159.0
HEAL_SPOT_Y = 108.0
# ─────────────────────────────────────────────────────────────────────────────


class State(Enum):
    ACTIVE = auto()     # watching HP, ready to nexus
    NEXUSING = auto()   # escape sent, burning cooldown ticks
    COOLDOWN = auto()   # in nexus, walking to heal spot and waiting for full HP


@dataclass
class SessionState:
    state: State = State.ACTIVE
    cooldown: int = 0


@plugin(active=True)
class AutoNexusPlugin:
    """Auto-nexus on low HP and re-arm once fully healed in nexus."""

    def __init__(self):
        self._sessionByGuid = {}
        self._healTarget = WorldPosData(HEAL_SPOT_X, HEAL_SPOT_Y)
        print(f"[AutoNexus] Loaded - nexus threshold={NEXUS_HP_THRESHOLD:.0%}")

    def _session(self, client):
        if client.guid not in self._sessionByGuid:
            self._sessionByGuid[client.guid] = SessionState()
        return self._sessionByGuid[client.guid]

    def _hpFraction(self, client):
        maxHp = client.playerData.maxHp
        curHp = client.playerData.hp
        if maxHp <= 0 or curHp < 0:
            return None
        return curHp / maxHp

    def _doNexus(self, client):
        session = self._session(client)
        client.nexus()
        session.state = State.NEXUSING
        session.cooldown = NEXUS_COOLDOWN_TICKS
        print(f"[AutoNexus:{client.alias}] HP critical - nexusing ({NEXUS_HP_THRESHOLD:.0%})")

    @hook("mapInfo")
    def onMapInfo(self, client, packet):
        # When we land in nexus after escape, keep NEXUSING/COOLDOWN flow alive.
        # For every other map transition, reset to ACTIVE.
        if client.gameId != GameIds.nexus:
            self._sessionByGuid[client.guid] = SessionState()

    @hook("newTick")
    def onNewTick(self, client, packet):
        hp = self._hpFraction(client)
        if hp is None:
            return

        session = self._session(client)

        if session.state == State.ACTIVE:
            if hp < NEXUS_HP_THRESHOLD:
                self._doNexus(client)
            return

        if session.state == State.NEXUSING:
            # Burn down cooldown to let map transition complete before walking.
            if session.cooldown > 0:
                session.cooldown -= 1
                return

            if client.gameId == GameIds.nexus:
                client.nextPos = [self._healTarget]
                session.state = State.COOLDOWN
                print(f"[AutoNexus:{client.alias}] Walking to heal spot ({HEAL_SPOT_X}, {HEAL_SPOT_Y})")
            return

        if session.state == State.COOLDOWN:
            if hp >= RESUME_HP_THRESHOLD:
                session.state = State.ACTIVE
                client.nextPos = []
                print(f"[AutoNexus:{client.alias}] HP fully restored - watching again")
