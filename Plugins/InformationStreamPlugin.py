from PluginManager import plugin, hook

# --- module-level public variables (other modules can import these) ---
current_player_data = None
current_hp = 0
max_hp = 0
current_mp = 0
max_mp = 0


@plugin(active=True)
class InformationStreamPlugin:
    def __init__(self):
        # minimal: keep a container for per-object usage if you later want to expand
        self.players = {}  # Track players by objectId like famefarm

    @hook("newTick")   # preserve the exact case your PluginManager expects
    def onNewTick(self, client, packet):
        """
        Use client's own playerData like other plugins do
        """
        global current_player_data, current_hp, max_hp, current_mp, max_mp

        try:
            if client.playerData:
                current_player_data = client.playerData

                # Update global variables for other plugins to use
                current_hp = getattr(current_player_data, 'hp', 0)
                max_hp = getattr(current_player_data, 'maxHp', 0)
                current_mp = getattr(current_player_data, 'mp', 0)
                max_mp = getattr(current_player_data, 'maxMp', 0)
        except AttributeError as e:
            # playerData doesn't exist yet
            print(f"[InformationStreamPlugin] AttributeError: {e}")
            pass
