from binascii import hexlify
import logging
from threading import Lock

from .block import GENESIS, GENESIS_HASH
from .utxoset import UTXOSet
from .validation import validate_block

log = logging.getLogger(__name__)


class Blockchain:
    """ Main class storing the current state of the blockchain. This stores all
    known blocks, validates them if possible and tracks the longest valid
    chain.

    Synchronisation works like this:
    Any block, which has been validated can no longer be changed. There is a
    lock to get the current head of the blockchain. To retrive some state, use
    Blockchain.get_head(). Any ancestor of the returned block is fixed, so can
    be read without problems.
    """
    def __init__(self):
        # Current state
        self.blocks_by_hash = {}
        self.utxos = UTXOSet()

        # Genesis block
        self.blocks_by_hash[GENESIS_HASH] = GENESIS
        self.unvalidated_blocks = {}
        self.head = GENESIS

        # Lock for the chain head and block lists
        self.lock = Lock()

        # Callbacks
        self.callback_lock = Lock()
        self.new_block_callbacks = []

    def get_head(self):
        """ Get head of the longest blockchain. Every ancestor is fixed, so
        walking up the chain for reading does not need further locking.

        Returns:
            A Block
        """
        with self.lock:
            head = self.head
        return head

    def add_block(self, block):
        """ Add a block to the known blocks. If possible, it will be validated.
        If a new longest chain gets known, the head is switched to the new
        chain. """
        block_hash = block.get_hash()
        with self.lock:
            if (block_hash in self.blocks_by_hash
                    or block_hash in self.unvalidated_blocks):
                # already known
                return

            try:
                parent = self.blocks_by_hash[block.prev_hash]
            except KeyError:
                # Store until we get the parent
                self.unvalidated_blocks[block_hash] = block
                # TODO: The parent should be requested from other nodes
                return

        block.set_parent(parent)
        if not validate_block(block, self.utxos):
            log.debug('Invalid block!')
            return

        # add to verified blocks
        with self.lock:
            self.blocks_by_hash[block_hash] = block

        # if block height is bigger than current, swap chain
        swapped = False
        with self.lock:
            if block.get_height() > self.head.get_height():
                swapped = True
                old_head = self.head
                self.utxos.move_on_chain(block)
                self.head = block

        if swapped:
            # Log if reorg
            if block.get_parent() != old_head:
                reorg_depth = (
                    old_head.get_height() -
                    block.find_common_ancestor(old_head).get_height()
                )
                log.info('A longer blockchain was found.'
                         'Reorganizing %i blocks...'
                         % reorg_depth)

            log.info("New blockchain height %i at %s"
                     % (block.get_height(), hexlify(block_hash)))

            # Inform callbacks about the new block
            with self.callback_lock:
                for func in self.new_block_callbacks:
                    func(self.head)

        # Check if other blocks can be validated now
        with self.lock:
            retry_blocks = {h: b for h, b
                            in self.unvalidated_blocks.items()
                            if b.prev_hash == block_hash}
            for h in retry_blocks.keys():
                self.unvalidated_blocks.pop(h)

        for b in retry_blocks.values():
            self.add_block(b)

    def register_new_block_callback(self, func):
        """ Register a function to be called, when the head of the blockchain
        changes.

        Args:
            func(function): A function, which takes one Block argument (the new
                            head)
        """
        with self.callback_lock:
            self.new_block_callbacks.append(func)

    def unregister_new_block_callback(self, func):
        """ Remove a function from the new block callback list. Note that the
        function object should be the same as was passed for registering.
        """
        with self.callback_lock:
            self.new_block_callbacks.remove(func)
