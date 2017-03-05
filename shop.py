#!/usr/bin/env python3

from binascii import hexlify
import logging
import select
import socketserver
from time import sleep

from shitcoin.blockchain import Blockchain
from shitcoin.miner import Miner
from shitcoin.mock_p2p import P2P
from shitcoin.wallet import Wallet

log = logging.getLogger(__name__)

FLAG = b'flagbot{XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX}'

SHOP_PORT = 8327
BLOCKCHAIN_PORT = 0  # Change to fix the port


class Shop(socketserver.StreamRequestHandler):
    def handle(self):
        # Blockchain and Wallet
        self.blockchain = Blockchain()
        self.wallet = Wallet(self.blockchain, autoload=False)

        # Create miner
        self.miner_address = self.wallet.new_address()
        self.miner = Miner(self.blockchain, self.miner_address, True)

        # Start blockchain server
        self.p2p = P2P(self.blockchain, self.miner, port=BLOCKCHAIN_PORT,
                       listen=True)
        # Wait for server to choose a port (awesome synchronisation)
        sleep(0.1)

        # Start mining
        self.miner.start_mining()

        # Wait until some blocks are mined
        while self.blockchain.head.get_height() < 10:
            self.poll_miner()
            sleep(0.1)

        # Shop
        self.shop_address = self.wallet.new_address()
        self.wfile.write(b'Welcome to our blockchain based shop!\n'
                         b'Currently we are out of everything, except one '
                         b'FLAG. To buy it, simply send the fair price of '
                         b'1,990,000 Shitcoin (STC) to %s!\n'
                         % hexlify(self.shop_address))

        self.wfile.write(b'Our blockchain has not found many users yet, but '
                         b'you can find a node at port %i\n' % self.p2p.port)

        last_balance = 0
        while True:
            # Handle network events
            self.poll_net()

            # Handle blocks from miner
            self.poll_miner()

            new_balance = self.wallet.get_balance(self.shop_address)
            if new_balance != last_balance:
                self.wfile.write(b'Thank you for your payment over %i STC! '
                                 b'You have paid a total of %i STC now.\n'
                                 % (new_balance - last_balance, new_balance))
                if new_balance >= 1990000:
                    self.wfile.write(b'Thank you for your purchase! Incredible'
                                     b' wealth you got there!\n%s\n' % FLAG)
                last_balance = new_balance

            # Check for remote disconnect
            r, _, _ = select.select([self.rfile], [], [], 0)
            if r:
                data = self.rfile.read(1000)
                if data == b'':
                    # Remote disconnected
                    log.info('Remote disconnected.')
                    self.miner.stop_mining()
                    self.p2p.shutdown()
                    return

            sleep(0.01)

    def poll_net(self):
        blocks_received = self.p2p.get_incoming_blocks()
        for blk in blocks_received:
            self.blockchain.add_block(blk)

        txs_received = self.p2p.get_incoming_transactions()
        for tx in txs_received:
            self.miner.add_transaction(tx)

    def poll_miner(self):
        mined_block = self.miner.get_mined_block()
        # local blocks cheat difficulty
        if mined_block is not None:
            mined_block.reduce_diff = True
            self.blockchain.add_block(mined_block)
            self.p2p.broadcast_block(mined_block)


if __name__ == "__main__":
    logging.basicConfig(level=10)
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(('0.0.0.0', SHOP_PORT), Shop)
    server.serve_forever()
