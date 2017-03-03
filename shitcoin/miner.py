from binascii import hexlify
from functools import partial
import logging
from os import urandom
import struct
from threading import Thread, Event, Lock
import time

from . import crypto
from .block import Block
from .crypto import HASH_LEN
from .mempool import Mempool
from .settings import INITIAL_REWARD, REWARD_HALVING_LEN
from .transaction import Transaction, Output, Input

log = logging.getLogger(__name__)


class MinerIsRunningException(Exception):
    pass


class MinerIsNotRunningException(Exception):
    pass


class Miner:
    def __init__(self, blockchain, found_block_callback, pubkey):
        self.blockchain = blockchain
        self.mempool = Mempool(blockchain)
        self.mining_thread = None
        self.found_block_callback = found_block_callback
        self.pubkey = pubkey

        # mining thread
        self.lock = Lock()
        self.target_block = None
        self.hashrate = 0.

        # Events
        self.stop_event = Event()
        self.retarget_event = Event()

    def add_transaction(self, tx):
        self.mempool.add_transaction(tx)

    def set_reward_address(self, pubkey):
        self.pubkey = pubkey

    def start_mining(self):
        if self.mining_thread is not None:
            raise MinerIsRunningException('Miner is already running!')

        log.info('Starting miner thread...')
        # Prepare new block
        self.build_block()
        self.blockchain.register_new_block_callback(
            partial(Miner.incoming_block, self))
        self.mempool.register_new_tx_callback(
            partial(Miner.mempool_updated, self))

        # Clear events
        self.stop_event.clear()

        # Start mining thread
        self.mining_thread = Thread(target=Miner.mine, name='miner',
                                    args=(self,), daemon=True)
        self.mining_thread.start()

    def stop_mining(self):
        if self.mining_thread is None:
            raise MinerIsNotRunningException('Miner is not running!')

        log.info('Stopping miner thread...')
        self.stop_event.set()
        self.mining_thread.join(10)
        if self.mining_thread.is_alive():
            log.error('Error stopping mining: Mining thread seems to be still '
                      'running after 10 seconds, giving up...')

        self.mining_thread = None

    def mine(self):
        # The nonce is 16 bytes. We use constant low 8 bytes to not collide
        # with other miners. We will not finish the upper 8 bytes anyways
        highnonce = urandom(8)
        log.info("Miner thread starting...")
        log.debug("Mining with nonce %sxxxxxxxxxxxxxxxx"
                  % hexlify(highnonce).decode('utf-8'))
        while True:
            self.retarget_event.clear()
            with self.lock:
                target_block = self.target_block
            # Prefix is block header, remove the nonce, add half our nonce
            prefix = target_block.serialize_header().get_bytes()[:-16]
            prefix += highnonce
            target_hash = 1 << (8 * HASH_LEN - target_block.diff)
            lownonce = 0
            log.debug('New mining target is %064x at blockheight %i.'
                      % (target_hash, target_block.get_height()))
            while not self.retarget_event.is_set():
                start_time = time.time()
                for i in range(100000):  # do 100k hashes
                    h = crypto.h(prefix + struct.pack('>Q', lownonce))
                    if int.from_bytes(h, byteorder='big') < target_hash:
                        # Found a block!
                        log.info("Found a block: %s!" % hexlify(h))
                        print(prefix + struct.pack('>Q', lownonce))
                        target_block.nonce = lownonce + (
                            int.from_bytes(highnonce, byteorder='big') << 64)
                        log.info("recalc: %s" % hexlify(target_block.get_hash()))
                        print(target_block.serialize_header().get_bytes())
                        if target_block.get_hash() != h:
                            raise Exception()
                        self.found_block_callback(target_block)
                        break
                    lownonce += 1

                if i == 99999:
                    with self.lock:
                        self.hashrate = 100 / (time.time() - start_time)

                if self.stop_event.is_set():
                    return

    def incoming_block(self, _):
        self.build_block()

    def mempool_updated(self, _):
        self.build_block()

    def build_block(self):
        # Build a block from all known transactions
        blk = Block()
        blk.set_parent(self.blockchain.head)
        blk.prev_hash = self.blockchain.head.get_hash()
        blk.timestamp = int(time.time())
        blk.diff = self.blockchain.head.get_next_diff()
        blk.add_transactions(self.mempool.transactions.values())

        # Add coinbase
        reward = INITIAL_REWARD // (2 ** (
            blk.get_height() // REWARD_HALVING_LEN))
        reward += self.mempool.total_fees
        coinbase_out = Output(reward, self.pubkey)
        coinbase_out.block = blk
        coinbase_inp = Input()  # dummy input to make the txid unique
        coinbase_inp.index = int.from_bytes(urandom(4), byteorder='big')
        coinbase = Transaction()
        coinbase.outputs = [coinbase_out]
        coinbase.inputs = [coinbase_inp]
        blk.txs.append(coinbase)

        blk.update_merkle_root()
        with self.lock:
            self.target_block = blk

        # Signal miner thread
        self.retarget_event.set()
