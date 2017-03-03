import struct

MASK16 = 0xffff
MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
MASK128 = (1 << 128) - 1


class SerializationBuffer:
    def __init__(self, buf=b''):
        self.buf = buf

    def get_bytes(self):
        """ Get the stored buffer """
        return self.buf

    def write(self, data):
        self.buf = self.buf + data

    def write_u8(self, v):
        self.write(struct.pack(">B", v))

    def write_u16(self, v):
        self.write(struct.pack(">H", v))

    def write_u32(self, v):
        self.write(struct.pack(">I", v))

    def write_u64(self, v):
        self.write(struct.pack(">Q", v))

    def write_u128(self, v):
        self.write(struct.pack(">Q", v >> 64)
                   + struct.pack(">Q", v & MASK64)
                   )

    def write_varuint(self, v):
        if v < 0xfc:
            self.write_u8(v)
        elif v <= MASK16:
            self.write_u8(0xfc)
            self.write_u16(v)
        elif v <= MASK32:
            self.write_u8(0xfd)
            self.write_u16(v)
        elif v <= MASK64:
            self.write_u8(0xfe)
            self.write_u64(v)
        elif v <= MASK128:
            self.write_u8(0xff)
            self.write_u128(v)
        else:
            raise ValueError('Trying to pack a number too large for varuint')

    def read(self, n):
        v = self.buf[:n]
        self.buf = self.buf[n:]
        return v

    def read_u8(self):
        return ord(self.read(1))

    def read_u16(self):
        return struct.unpack(">H", self.read(2))[0]

    def read_u32(self):
        return struct.unpack(">I", self.read(4))[0]

    def read_u64(self):
        return struct.unpack(">Q", self.read(8))[0]

    def read_u128(self):
        high = struct.unpack(">Q", self.read(8))[0]
        low = struct.unpack(">Q", self.read(8))[0]
        return (high << 64) | low

    def read_varuint(self):
        b = self.read_u8()
        if b < 0xfc:
            return b
        if b == 0xfc:
            return self.read_u16()
        if b == 0xfd:
            return self.read_u32()
        if b == 0xfe:
            return self.read_u64()
        if b == 0xff:
            return self.read_u128()
