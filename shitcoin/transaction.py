from . import crypto
from .crypto import PUBKEY_LEN, HASH_LEN, SIG_LEN, NO_HASH, NO_SIG, NO_PUBKEY
from .serialize import SerializationBuffer


class Output:
    def __init__(self, amount=0, pubkey=NO_PUBKEY):
        self.amount = amount
        self.pubkey = pubkey

        # References
        self.block = None

    @staticmethod
    def unserialize(buf):
        output = Output()
        output.amount = buf.read_varuint()
        output.pubkey = buf.read(PUBKEY_LEN)
        return output

    def serialize(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()
        buf.write_varuint(self.amount)
        buf.write(self.pubkey)
        return buf

    def __repr__(self):
        return "<Output %s: %i>" % (self.pubkey, self.amount)


class Input:
    def __init__(self, txid=NO_HASH, index=0, signature=NO_SIG):
        self.txid = txid
        self.index = index
        self.signature = signature

        # References
        self.spent_output = None

    @staticmethod
    def unserialize(buf):
        input = Input()
        input.txid = buf.read(HASH_LEN)
        input.index = buf.read_u32()
        input.signature = buf.read(SIG_LEN)
        return input

    def serialize(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        buf.write(self.txid)
        buf.write_u32(self.index)
        buf.write(self.signature)
        return buf

    def serialize_no_sig(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        buf.write(self.txid)
        buf.write_u32(self.index)
        return buf


class Transaction:
    def __init__(self):
        self.inputs = []
        self.outputs = []

    @staticmethod
    def unserialize(buf):
        tx = Transaction()
        inputCount = buf.read_varuint()
        for _ in range(inputCount):
            tx.inputs.append(Input.unserialize(buf))
        outputCount = buf.read_varuint()
        for _ in range(outputCount):
            tx.outputs.append(Output.unserialize(buf))
        return tx

    def serialize(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        buf.write_varuint(len(self.inputs))
        for inp in self.inputs:
            inp.serialize(buf)
        buf.write_varuint(len(self.outputs))
        for out in self.outputs:
            out.serialize(buf)
        return buf

    def serialize_no_sig(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        buf.write_varuint(len(self.inputs))
        for inp in self.inputs:
            inp.serialize_no_sig(buf)
        buf.write_varuint(len(self.outputs))
        for out in self.outputs:
            out.serialize(buf)
        return buf

    def get_txid(self):
        """ Get the transaction ID. The transaction ID is the hash of the
        transaction without signatures. The signatures are excluded, so they
        do not have to sign themselves... Also malleability. """
        return crypto.h(self.serialize_no_sig().get_bytes())
