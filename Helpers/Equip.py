class Weapon:
    def __init__(self, obj):
        self.parse(obj)

    def parse(self, obj):
        self.name = obj.attrib["id"]
        self.itemId = int(obj.attrib["type"], 16)

        rof = obj.find("RateOfFire")
        self.rof = float(rof.text) if rof is not None else 1.0

        numProj = obj.find("NumProjectiles")
        self.numProjectiles = int(numProj.text) if numProj is not None else 1

        arcGap = obj.find("ArcGap")
        self.arcGap = float(arcGap.text) if arcGap is not None else 11.25

        self.projectile = Projectile(obj.find("Projectile"))
        

class Projectile:
    def __init__(self, proj):
        self.parse(proj)

    def parse(self, proj):
        speed = proj.find("Speed")
        self.speed = float(speed.text) if speed is not None else 100.0

        lifetime = proj.find("LifetimeMS")
        self.lifetime = float(lifetime.text) if lifetime is not None else 1000.0

        dmg = proj.find("Damage")
        if dmg is not None:
            self.minDmg = int(dmg.text)
            self.maxDmg = self.minDmg
        else:
            minDmg = proj.find("MinDamage")
            maxDmg = proj.find("MaxDamage")
            self.minDmg = int(minDmg.text) if minDmg is not None else 0
            self.maxDmg = int(maxDmg.text) if maxDmg is not None else 0


from xml.etree import ElementTree

WEAPONIDS = [17, 8, 1, 24, 3, 2]

def parseWeapons(path):
    idToWeapon = {}
    tree = ElementTree.parse(path)
    root = tree.getroot()
    for obj in root:
        slotType = obj.find("SlotType")
        if slotType is None:
            continue
        if int(slotType.text) not in WEAPONIDS:
            continue

        try:
                weapon = Weapon(obj)
                idToWeapon[weapon.itemId] = weapon
        except Exception as e:
            print(f"[Equip] Skipping '{obj.attrib.get('id', '?')}': {e}")

    return idToWeapon
