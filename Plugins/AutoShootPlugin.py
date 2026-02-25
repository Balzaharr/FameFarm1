from dataclasses import dataclass
import math

from Constants import ClassIds
from Constants.StatTypes import StatTypes
from PluginManager import hook, plugin


@dataclass
class EnemyState:
    objectId: int
    x: float
    y: float
    hp: int = -1


@plugin(active=True)
class AutoShootPlugin:
    """Very basic auto-shoot plugin.

    Controls (private message to the running character):
      - autoshoot on
      - autoshoot off
      - autoshoot
    """

    def __init__(self):
        self.enabledByGuid = {}
        self.enemiesByGuid = {}

    def _isEnabled(self, client):
        return self.enabledByGuid.get(client.guid, False)

    def _setEnabled(self, client, enabled):
        self.enabledByGuid[client.guid] = enabled

    def _enemyMap(self, client):
        if client.guid not in self.enemiesByGuid:
            self.enemiesByGuid[client.guid] = {}
        return self.enemiesByGuid[client.guid]

    def _extractHp(self, stats):
        for stat in stats:
            if stat.statType == StatTypes.HPSTAT:
                return stat.statValue
        return -1

    @hook("mapInfo")
    def onMapInfo(self, client, packet):
        self.enemiesByGuid[client.guid] = {}

    @hook("update")
    def onUpdate(self, client, packet):
        enemies = self._enemyMap(client)

        for droppedId in packet.drops:
            enemies.pop(droppedId, None)

        for obj in packet.newObjs:
            if obj.status.objectId == client.objectId:
                continue
            if obj.objectType in ClassIds.ALL:
                continue

            hp = self._extractHp(obj.status.stats)
            if hp == 0:
                continue

            enemies[obj.status.objectId] = EnemyState(
                objectId=obj.status.objectId,
                x=obj.status.pos.x,
                y=obj.status.pos.y,
                hp=hp,
            )

    @hook("newTick")
    def onNewTick(self, client, packet):
        enemies = self._enemyMap(client)

        for status in packet.statuses:
            enemy = enemies.get(status.objectId)
            if enemy is None:
                continue

            enemy.x = status.pos.x
            enemy.y = status.pos.y

            hp = self._extractHp(status.stats)
            if hp != -1:
                enemy.hp = hp
                if hp <= 0:
                    enemies.pop(status.objectId, None)

        if not self._isEnabled(client):
            return
        if client.pos is None or len(enemies) == 0:
            return

        target = min(
            enemies.values(),
            key=lambda e: (client.pos.x - e.x) ** 2 + (client.pos.y - e.y) ** 2,
        )

        angle = math.atan2(target.y - client.pos.y, target.x - client.pos.x)
        client.shoot(angle)

    @hook("text")
    def onText(self, client, packet):
        if packet.recipient != client.playerData.name:
            return

        msg = packet.text.strip().lower()
        if msg == "autoshoot on":
            self._setEnabled(client, True)
            print(f"[{client.alias}] autoshoot enabled")
        elif msg == "autoshoot off":
            self._setEnabled(client, False)
            print(f"[{client.alias}] autoshoot disabled")
        elif msg == "autoshoot":
            newState = not self._isEnabled(client)
            self._setEnabled(client, newState)
            print(f"[{client.alias}] autoshoot {'enabled' if newState else 'disabled'}")
