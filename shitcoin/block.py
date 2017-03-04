from binascii import hexlify
import logging
import time

from . import crypto
from .crypto import HASH_LEN, NO_HASH
from .serialize import SerializationBuffer
from .settings import (
    GENESIS_PREVHASH,
    GENESIS_TIME
)
from .transaction import Transaction

log = logging.getLogger(__name__)


class Block:
    def __init__(self):
        self.prev_hash = NO_HASH
        self.merkle_root = NO_HASH
        self.timestamp = int(time.time())
        self.nonce = 0
        self.diff = 1
        self.txs = []

        self._parent = None
        self._height = -1

    def set_parent(self, parent):
        self._parent = parent
        self._height = parent._height + 1

    def get_parent(self):
        return self._parent

    def get_height(self):
        return self._height

    def get_hash(self):
        return crypto.h(self.serialize_header().get_bytes())

    def __eq__(self, other):
        if not isinstance(other, Block):
            return False

        # Start with small things to quickly get false results
        # Transactions are not checked, so this is only good for validated
        # transactions, where the merkle root is correct
        if (self.nonce == other.nonce
                and self.diff == other.diff
                and self.timestamp == other.timestamp
                and self.prev_hash == other.prev_hash
                and self.merkle_root == other.merkle_root):
            return True
        return False

    def __repr__(self):
        return "<Block %s>" % hexlify(self.get_hash())

    def add_transactions(self, txs):
        for tx in txs:
            for out in tx.outputs:
                out.block = self
            self.txs.append(tx)

    @staticmethod
    def unserialize(buf):
        blk = Block()
        blk.prev_hash = buf.read(HASH_LEN)
        blk.merkle_root = buf.read(HASH_LEN)
        blk.timestamp = buf.read_u64()
        blk.diff = buf.read_u8()
        blk.nonce = buf.read_u64()
        txcount = buf.read_u32()
        blk.txs = []
        for _ in range(txcount):
            blk.txs.append(Transaction.unserialize(buf))

        # Set parent references of all outputs
        for tx in blk.txs:
            for out in tx.outputs:
                out.block = blk
        return blk

    def serialize(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        self.serialize_header(buf)
        buf.write_u32(len(self.txs))
        for tx in self.txs:
            tx.serialize(buf)
        return buf

    def serialize_header(self, buf=None):
        if buf is None:
            buf = SerializationBuffer()

        buf.write(self.prev_hash)
        buf.write(self.merkle_root)
        buf.write_u64(self.timestamp)
        buf.write_u8(self.diff)
        buf.write_u64(self.nonce)
        return buf

    def update_merkle_root(self):
        tx_bufs = [tx.serialize().get_bytes() for tx in self.txs]
        self.merkle_root = crypto.merkle_root(tx_bufs)
        self._validated = False

    def find_common_ancestor(self, other_block):
        block1 = self if self._height > other_block._height else other_block
        block2 = other_block if self._height > other_block._height else self

        # rewind block1 to same height as block2
        for _ in range(block1.get_height() - block2.get_height()):
            block1 = block1.get_parent()

        # If one was the ancestor of the other, we found the target
        if block1 == block2:
            return block1

        # Now go back until they have the same parent
        while block1.prev_hash != block2.prev_hash:
            block1 = block1.get_parent()
            block2 = block2.get_parent()

        return block1.get_parent()


# Genesis block
GENESIS = Block()
GENESIS._height = 0
GENESIS._parent = GENESIS
GENESIS.prev_hash = GENESIS_PREVHASH
GENESIS.timestamp = GENESIS_TIME
GENESIS.update_merkle_root()

GENESIS_HASH = GENESIS.get_hash()
