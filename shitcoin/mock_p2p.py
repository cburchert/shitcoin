""" Shitty P2P with a maximum of 2 nodes. """
from binascii import hexlify
import logging
import select
import socket
import struct
from threading import Thread, Lock, Event
from time import sleep

from shitcoin.block import Block
from shitcoin.serialize import SerializationBuffer
from shitcoin.transaction import Transaction

log = logging.getLogger(__name__)


class P2P:
    def __init__(self, blockchain, miner, host='0.0.0.0', port=0,
                 listen=False):
        self.blockchain = blockchain
        self.miner = miner
        self.listen = listen
        self.host = host
        self.port = port

        # Communication to network thread
        self.lock = Lock()
        self.stop_event = Event()
        self.blocks_to_send = []
        self.blocks_received = []
        self.txs_to_send = []
        self.txs_received = []

        self.net_thread = Thread(target=P2P.net_main, name='net',
                                 args=(self,), daemon=True)
        self.net_thread.start()

    def shutdown(self):
        """ Disconnect and stop the network thread """
        log.info('Stopping p2p thread...')
        self.stop_event.set()
        self.net_thread.join(10)
        if self.net_thread.is_alive():
            raise Exception("Could not stop network thread!")

    def broadcast_block(self, block):
        with self.lock:
            self.blocks_to_send.append(block)

    def broadcast_transaction(self, tx):
        with self.lock:
            self.txs_to_send.append(tx)

    def net_main(self):
        if self.listen:
            self.srv = socket.socket()
            self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.srv.bind((self.host, self.port))
            self.port = self.srv.getsockname()[1]
            self.srv.listen(1)
            self.sock, peer_addr = self.srv.accept()
            log.info('Peer connected from %s:%i' % peer_addr)
        else:
            self.sock = socket.socket()
            self.sock.connect((self.host, self.port))
        recv_buf = b''

        while True:
            with self.lock:
                blocks_to_send = self.blocks_to_send
                self.blocks_to_send = []

            for blk in blocks_to_send:
                buf = SerializationBuffer()
                buf.write(b'BLK')
                blk.serialize(buf)

                data = buf.get_bytes()
                self.sock.send(struct.pack(">I", len(data)) + data)

            with self.lock:
                txs_to_send = self.txs_to_send
                self.txs_to_send = []

            for tx in txs_to_send:
                buf = SerializationBuffer()
                buf.write(b'TXN')
                tx.serialize(buf)
                data = buf.get_bytes()
                self.sock.send(struct.pack(">I", len(data)) + data)

            r, _, _ = select.select([self.sock], [], [], 0)
            if r:
                recv_buf += self.sock.recv(100000)

                while True:
                    if len(recv_buf) < 4:
                        break
                    pkg_len = struct.unpack(">I", recv_buf[:4])[0]
                    if len(recv_buf) < pkg_len + 4:
                        break
                    pkg = recv_buf[4:pkg_len+4]
                    recv_buf = recv_buf[pkg_len+4:]
                    self.parse_pkg(self.sock, pkg)

            if self.stop_event.is_set():
                return
            sleep(0.1)

    def parse_pkg(self, sock, pkg):
        buf = SerializationBuffer(pkg)
        typ = buf.read(3)

        if typ == b'BLK':
            blk = Block.unserialize(buf)
            log.debug("Received block %s" % hexlify(blk.get_hash()))
            with self.lock:
                self.blocks_received.append(blk)
        elif typ == b'TXN':
            tx = Transaction.unserialize(buf)
            log.debug("Received tx %s" % hexlify(tx.get_txid()))
            with self.lock:
                self.txs_received.append(tx)
        elif typ == b'REQ':
            # block request
            try:
                block_hash = buf.read(32)
                log.debug('Peer requested block %s' % hexlify(block_hash))
                blk = self.blockchain.blocks_by_hash[block_hash]
            except KeyError:
                sock.send('Shitty peer.')
                sock.close()
            resp_buf = SerializationBuffer()
            resp_buf.write(b'BLK')
            blk.serialize(resp_buf)
            data = resp_buf.get_bytes()
            sock.send(struct.pack(">I", len(data)) + data)

    def get_incoming_transactions(self):
        with self.lock:
            txs_received = self.txs_received
            self.txs_received = []

        return txs_received

    def get_incoming_blocks(self):
        with self.lock:
            blocks_received = self.blocks_received
            self.blocks_received = []

        return blocks_received
