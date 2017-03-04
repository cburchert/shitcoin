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
    def __init__(self, blockchain, pubkey):
        self.blockchain = blockchain
        self.mempool = Mempool(blockchain)
        self.mining_thread = None
        self.pubkey = pubkey

        # mining thread. These variables are protected with the lock
        self.lock = Lock()
        self.target_block = None
        self.hashrate = 0.
        self.mined_block = None

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

        self.blockchain.register_new_block_callback(
            partial(Miner.retarget, self))
        self.mempool.register_new_tx_callback(
            partial(Miner.retarget, self))

        # Clear events
        self.stop_event.clear()
        self.retarget_event.clear()

        # Prepare new block
        self.retarget()

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

    def get_hashrate(self):
        if self.mining_thread is None:
            raise MinerIsNotRunningException('Miner is not running!')

        with self.lock:
            return self.hashrate

    def mine(self):
        log.info("Miner thread starting...")
        nonce = int.from_bytes(urandom(4), byteorder='big')

        while True:
            # Wait for a target
            target_block = None
            while target_block is None:
                with self.lock:
                    target_block = self.target_block
                    self.retarget_event.clear()

            # Prefix is block header, remove the nonce
            prefix = target_block.serialize_header().get_bytes()[:-8]
            target_hash = 1 << (8 * HASH_LEN - target_block.diff)
            log.debug('New mining target is %064x at blockheight %i.'
                      % (target_hash, target_block.get_height()))

            while not self.retarget_event.is_set():
                # Set up counters for hashrate
                start_time = time.time()
                start_nonce = nonce

                for _ in range(100000):  # do 100k hashes
                    h = crypto.h(prefix + struct.pack('>Q', nonce))
                    if int.from_bytes(h, byteorder='big') < target_hash:
                        log.info("Found a block: %s!" % hexlify(h))
                        target_block.nonce = nonce
                        with self.lock:
                            self.mined_block = target_block
                            self.target_block = None
                            self.retarget_event.set()
                        target_block = None
                        break
                    nonce += 1

                # Calculate hashrate
                hashrate = (nonce - start_nonce) / (time.time() - start_time)
                with self.lock:
                    self.hashrate = hashrate

                if self.stop_event.is_set():
                    return

    def get_mined_block(self):
        with self.lock:
            blk = self.mined_block
            self.mined_block = None
        return blk

    def retarget(self, _=None):
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
            self.retarget_event.set()
