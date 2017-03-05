import logging
import math
from statistics import median
import time

from . import crypto
from .crypto import HASH_LEN
from .exceptions import InvalidTransaction
from .settings import (
    BLOCK_TIME,
    DIFF_PERIOD_LEN,
    INITIAL_REWARD,
    REWARD_HALVING_LEN
)


log = logging.getLogger(__name__)


def validate_block(block, utxos):
    """ Validates the block with the given UTXO set. This applies the block to
    the utxos, so if you just want to validate the block without applying the
    transactions, copy the utxo set first. """
    if not validate_block_header(block):
        log.info("Invalid block header!")
        return False

    # Check Merkle root
    if block.merkle_root != crypto.merkle_root([tx.serialize().get_bytes()
                                                for tx in block.txs]):
        log.info("Incorrect merkle root!")
        return False

    # Check transactions
    utxos.move_on_chain(block.get_parent())
    try:
        money_created = utxos.apply_block(block, verify=True)
    except InvalidTransaction:
        log.info("Invalid transaction in block!")
        return False

    # Check block reward
    reward = INITIAL_REWARD // (2 ** (
        block.get_height() // REWARD_HALVING_LEN))
    if money_created > reward:
        log.info("Block creates too much money!")
        return False

    return True


def validate_block_header(block):
    # Check metadata is available
    if block._parent is None:
        return False
    if block._height == -1:
        return False
    if block.prev_hash != block._parent.get_hash():
        return False

    # Check timestamp
    if block.timestamp > time.time() + 7200:
        log.info("Block is more than two hours into the future!")
        return False

    last_timestamps = []
    cur = block.get_parent()
    for _ in range(10):
        last_timestamps.append(cur.timestamp)
        cur = cur.get_parent()
    if block.timestamp < median(last_timestamps):
        log.info("Block is older than median of last 10 blocks!")
        return False

    # Check difficulty
    if block.diff != get_next_diff(block.get_parent()):
        return False

    # Check Proof-of-Work
    diff = block.diff
    if getattr(block, 'reduce_diff', False):
        # If the flag is set, the block is 1024 times easier
        diff = max(block.diff - 10, 1)
    block_hash = block.get_hash()
    if int.from_bytes(block_hash, byteorder='big') >> (
            8 * HASH_LEN - diff) != 0:
        return False

    return True


def get_next_diff(block):
    """ Get the difficulty, the block following the supplied one must have. """
    # During one period, keep the same diff
    if (block.get_height() + 1) % DIFF_PERIOD_LEN != 0:
        return block.diff

    # Beginning of new difficulty period
    # Get how long the last period took
    first_block = block
    for _ in range(DIFF_PERIOD_LEN - 2):
        first_block = first_block.get_parent()
    timediff = block.timestamp - first_block.timestamp

    # Fix zero timediff at low difficulties
    if timediff == 0:
        timediff = 1

    # Adjust diff, so next period has correct time
    next_diff = int(
        math.log((2 ** block.diff) * BLOCK_TIME * DIFF_PERIOD_LEN
                 / timediff, 2))
    if next_diff <= 0:
        next_diff = 1
    return next_diff
