from binascii import hexlify
import logging

from .block import Block
from . import crypto
from .settings import (
    GENESIS_PREVHASH,
    GENESIS_TIME,
    REWARD_HALVING_LEN,
    INITIAL_REWARD
)
from .utxoset import InvalidTransaction, UTXOSet

log = logging.getLogger(__name__)


class Blockchain:
    """ Main class storing the current state of the blockchain. This stores all
    known blocks, validates them if possible and tracks the longest chain."""
    def __init__(self):
        # Current state
        self.blocks_by_hash = {}
        self.utxos = UTXOSet()

        # Genesis block
        genesis = Block()
        genesis._height = 0
        genesis._parent = genesis
        genesis.prev_hash = GENESIS_PREVHASH
        genesis.timestamp = GENESIS_TIME
        genesis.update_merkle_root()
        genesis_hash = genesis.get_hash()
        self.blocks_by_hash[genesis_hash] = genesis

        self.head = genesis

        # Other stuff we know
        self.unvalidated_blocks = {}

        # Callbacks
        self.new_block_callbacks = []

    def validate_block(self, block):
        if not block.is_header_valid():
            log.info("Invalid block header!")
            return False

        # Check transactions
        temp_utxos = self.utxos.copy()
        temp_utxos.move_on_chain(self.head, block.get_parent())
        try:
            money_created = temp_utxos.apply_block(block, verify=True)
        except InvalidTransaction:
            log.info("Invalid transaction in block!")
            return False

        # Check block reward
        reward = INITIAL_REWARD // (2 ** (
            block.get_height() // REWARD_HALVING_LEN))
        if money_created > reward:
            log.info("Block creates too much money!")
            return False

        # Check Merkle root
        if block.merkle_root != crypto.merkle_root([tx.serialize().get_bytes()
                                                    for tx in block.txs]):
            log.info("Incorrect merkle root!")
            return False

        block.was_here = True

        return True

    def add_block(self, block):
        block_hash = block.get_hash()
        if (block_hash in self.blocks_by_hash
                or block_hash in self.unvalidated_blocks):
            # already known
            return

        if block.prev_hash in self.blocks_by_hash:
            # awesome, lets validate it
            block.set_parent(self.blocks_by_hash[block.prev_hash])
            if self.validate_block(block):
                # add to verified blocks
                self.blocks_by_hash[block_hash] = block
                # if block height is bigger than current, swap chain
                if block.get_height() > self.head.get_height():
                    self.utxos.move_on_chain(self.head, block)
                    self.head = block
                    log.info("New blockchain height %i at %s"
                             % (self.head.get_height(), hexlify(block_hash)))
                    # Inform callbacks about the new block
                    for func in self.new_block_callbacks:
                        func(self.head)

                # Check if other blocks can be validated now
                retry_blocks = [b for b in self.unvalidated_blocks
                                if b.prevHash == block_hash]
                for b in retry_blocks:
                    self.unvalidated_blocks.remove(b)
                    self.add_block(b)

            else:
                # bad block
                log.debug('Invalid block!')
                return

        else:
            # Store until we get the parent
            self.unvalidated_blocks[block_hash] = block

    def register_new_block_callback(self, func):
        """ Register a function to be called, when the head of the blockchain
        changes. """
        self.new_block_callbacks.append(func)

    def unregister_new_block_callback(self, func):
        """ Remove a function from the new block callback list. Note that the
        function object should be the same as was passed for registering. """
        self.new_block_callbacks.remove(func)
