from binascii import hexlify
import logging
import math
import time

from . import crypto
from .crypto import HASH_LEN, NO_HASH
from .serialize import SerializationBuffer
from .settings import (
    DIFF_PERIOD_LEN,
    BLOCK_TIME
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

        self._validated = False
        self._valid = False
        self._parent = None
        self._height = -1

    def set_parent(self, parent):
        self._parent = parent
        self._height = parent._height + 1
        self._validated = False

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
        blk.nonce = buf.read_u128()
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
        buf.write_u128(self.nonce)
        return buf

    def update_merkle_root(self):
        tx_bufs = [tx.serialize().get_bytes() for tx in self.txs]
        self.merkle_root = crypto.merkle_root(tx_bufs)
        self._validated = False

    def get_next_diff(self):
        if (self._height + 1) % DIFF_PERIOD_LEN != 0:
            return self.diff

        # Beginning of new difficulty period
        # Get how long the last period took
        first_block = self
        for _ in range(DIFF_PERIOD_LEN - 2):
            first_block = first_block._parent
        timediff = self.timestamp - first_block.timestamp

        # Fix zero timediff at low difficulties
        if timediff == 0:
            timediff = 1

        # Adjust diff, so next period has correct time
        next_diff = int(
            math.log((2 ** self.diff) * BLOCK_TIME * DIFF_PERIOD_LEN
                     / timediff, 2))
        if next_diff == 0:
            next_diff = 1
        return next_diff

    def is_header_valid(self):
        # Check metadata is available
        log.debug('checking block')
        if self._parent is None:
            return False
        if self._height == -1:
            return False
        if self._validated:
            return self._valid
        if self.prev_hash != self._parent.get_hash():
            return False
        log.debug('parent is good.')

        # Check difficulty
        if self.diff != self._parent.get_next_diff():
            return False
        log.debug('diff is good.')

        # Check Proof-of-Work
        block_hash = self.get_hash()
        print(hexlify(block_hash))
        if int.from_bytes(block_hash, byteorder='big') >> (
                8 * HASH_LEN - self.diff) != 0:
            return False
        log.debug('all good')

        return True

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
