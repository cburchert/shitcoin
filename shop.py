#!/usr/bin/env python3

from binascii import hexlify
from functools import partial
import logging
import socketserver
from time import sleep

from shitcoin.blockchain import Blockchain
from shitcoin.miner import Miner
from shitcoin.mock_p2p import P2P
from shitcoin.wallet import Wallet

log = logging.getLogger(__name__)

FLAG = 'flagbot{They_did_not_fix_it_it_just_became_more_difficult}'

SHOP_PORT = 8327
BLOCKCHAIN_PORT = 8328


class Shop(socketserver.StreamRequestHandler):
    def handle(self):
        # Blockchain and Wallet
        self.blockchain = Blockchain()
        self.wallet = Wallet(self.blockchain, autoload=False)

        # Create miner
        self.miner_address = self.wallet.new_address()
        self.miner = Miner(self.blockchain, partial(Shop.mined_block, self),
                           self.miner_address)

        # Start blockchain server
        self.p2p = P2P(self.blockchain, self.miner, port=BLOCKCHAIN_PORT,
                       listen=True)
        # Wait for server to choose a port (awesome synchronisation)
        sleep(0.1)

        # Start mining
        self.miner.start_mining()

        # Wait until some blocks are mined
        while self.blockchain.head.get_height() < 10:
            sleep(0.1)

        # Shop
        self.shop_address = self.wallet.new_address()
        self.wfile.write(b'Welcome to our blockchain based shop!\n'
                         b'Currently we are out of everything, except one '
                         b'FLAG. To buy it, simply send the fair price of '
                         b'1,990,000 Shitcoin (STC) to %s!\n'
                         % hexlify(self.shop_address))

        self.wfile.write(b'Our blockchain has not found many users yet, but '
                         b'you can find a node at port %i\n' % BLOCKCHAIN_PORT)

        last_balance = 0
        while True:
            self.p2p.handle_incoming_data()
            new_balance = self.wallet.get_balance(self.shop_address)
            if new_balance != last_balance:
                self.wfile.write(b'Thank you for your payment over %i STC! '
                                 b'You have paid a total of %i STC now.\n'
                                 % (new_balance - last_balance, new_balance))
                if new_balance >= 1990000:
                    self.wfile.write(b'Thank you for your purchase! Incredible'
                                     b' wealth you got there!\n%s\n' % FLAG)
                last_balance = new_balance
            sleep(0.1)

    def mined_block(self, block):
        self.p2p.broadcast_block(block)
        self.blockchain.add_block(block)


if __name__ == "__main__":
    logging.basicConfig(level=10)
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(('127.0.0.1', SHOP_PORT), Shop)
    server.serve_forever()
