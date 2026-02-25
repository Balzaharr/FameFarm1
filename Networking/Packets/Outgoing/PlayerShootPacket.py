from Networking.Packets.Packet import Packet
from Data.WorldPosData import WorldPosData


class PlayerShootPacket(Packet):
    def __init__(self):
        self.type = "PLAYERSHOOT"
        self.time = 0
        self.bulletId = 0
        self.containerType = 0
        self.projectileId = 0
        self.shotPos = WorldPosData()
        self.angle = 0
        self.isBurst = False
        self.patternIdx = -1
        self.attackType = 0
        self.pos = WorldPosData()

    def write(self, writer):
        writer.writeInt32(self.time)
        writer.writeShort(self.bulletId)
        writer.writeShort(self.containerType)
        writer.writeByte(self.projectileId)
        self.shotPos.write(writer)
        writer.writeFloat(self.angle)
        writer.writeBool(self.isBurst)
        writer.writeByte(self.patternIdx)
        writer.writeByte(self.attackType)
        self.pos.write(writer)

    def read(self, reader):
        self.time = reader.readInt32()
        self.bulletId = reader.readShort()
        self.containerType = reader.readShort()
        self.projectileId = reader.readByte()
        self.shotPos.read(reader)
        self.angle = reader.readFloat()
        self.isBurst = reader.readBool()
        self.patternIdx = reader.readByte()
        self.attackType = reader.readByte()
        self.pos.read(reader)
