#!/usr/bin/env python3

from binascii import hexlify, unhexlify
from datetime import datetime
import logging
import socket
from sys import argv
from threading import Thread
from time import sleep
import traceback

from shitcoin.crypto import NO_PUBKEY, NO_HASH
from shitcoin.blockchain import Blockchain
from shitcoin.miner import Miner
from shitcoin.mock_p2p import P2P
from shitcoin.validation import get_next_diff
from shitcoin.wallet import Wallet, NotEnoughFunds


log = logging.getLogger(__name__)


class RPC:
    """ Awesome RPC interface. Totally ignores locking """
    def __init__(self, blockchain, miner, wallet, p2p):
        self.blockchain = blockchain
        self.miner = miner
        self.wallet = wallet
        self.p2p = p2p

        self.rpc_sock = socket.socket()
        self.rpc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rpc_sock.bind(('127.0.0.1', 7839))
        self.rpc_sock.listen(1)
        log.info('RPC server is listening on port 7839')

        self.rpc_thread = Thread(target=RPC.rpc_loop, name='rpc', args=(self,),
                                 daemon=True)
        self.rpc_thread.start()

    def rpc_loop(self):
        while True:
            buf = b''
            cli_sock, cli_addr = self.rpc_sock.accept()
            log.info('RPC connection from %s' % cli_addr.__repr__())
            cli_sock.send(b"Welcome to your shitcoin client's RPC interface.\n"
                          b'Commands:\n'
                          b'q: quit\n'
                          b'send <addr> <amount>: Send some currency\n'
                          b'new_address: Generate new address\n'
                          b'show_balance [address]: Show your balance\n'
                          b'show_wallet: Show owned balances by address\n'
                          b'start_mining <addr>: Start mining to address\n'
                          b'stop_mining: Stop mining\n'
                          b'show_hashrate: Show miners hashrate\n'
                          b'ascii <limit>: Ascii art blockchain\n')

            while True:
                cli_sock.send(b'>> ')

                while b'\n' not in buf:
                    buf += cli_sock.recv(1024)
                line = buf[:buf.find(b'\n')]
                buf = buf[buf.find(b'\n')+1:]
                args = line.strip().split(b' ')
                cmd = args[0]

                try:
                    if cmd == b'q':
                        cli_sock.close()
                        break

                    elif cmd == b'send':
                        try:
                            tx = self.wallet.create_transaction(
                                {unhexlify(args[1]): int(args[2])})
                            self.miner.add_transaction(tx)
                            self.p2p.broadcast_transaction(tx)
                        except NotEnoughFunds:
                            cli_sock.send(b'insufficient funds.\n')
                        else:
                            cli_sock.send(b'Transaction sent to miners.\n')

                    elif cmd == b'new_address':
                        addr = self.wallet.new_address()
                        cli_sock.send(b'%s\n' % hexlify(addr))

                    elif cmd == b'show_balance':
                        if len(args) > 1:
                            balance = self.wallet.get_balance(args[1])
                        else:
                            balance = self.wallet.get_balance()
                        cli_sock.send(b'%i\n' % balance)

                    elif cmd == b'show_wallet':
                        for addr in self.wallet.get_addresses():
                            cli_sock.send(b'%s: %i\n'
                                          % (hexlify(addr),
                                             self.wallet.get_balance(addr)))

                    elif cmd == b'start_mining':
                        addr = unhexlify(args[1])
                        if len(addr) != 32:
                            raise Exception('Bad address')
                        self.miner.set_reward_address(addr)
                        self.miner.start_mining()

                    elif cmd == b'stop_mining':
                        self.miner.stop_mining()

                    elif cmd == b'show_hashrate':
                        hashrate = self.miner.get_hashrate()
                        seconds_per_block = (
                            (2 ** get_next_diff(self.blockchain.get_head()))
                            / hashrate / 1000)
                        cli_sock.send(b'Hashrate is %.2f kH/s '
                                      b'(~ %.2f s per block)\n'
                                      % (hashrate, seconds_per_block))

                    elif cmd == b'ascii':
                        msg = self.asciiart(int(args[1]))
                        cli_sock.send(msg)
                    else:
                        cli_sock.send(b'Unknown command.\n')
                except Exception:
                    with cli_sock.makefile('w') as f:
                        traceback.print_exc(file=f)

    def asciiart(self, limit):
        msg = b''

        # make list of last limit blocks
        blocks = []
        cur = self.blockchain.head
        for _ in range(limit):
            blocks.append(cur)
            if cur.get_parent() != cur:
                cur = cur.get_parent()
            else:
                # break at genesis, which is parent of itself
                break
        blocks.reverse()

        for blk in blocks:
            msg += b'BLK %i %s\n' % (blk.get_height(), hexlify(blk.get_hash()))
            msg += b'- prev_hash: %s\n' % hexlify(blk.prev_hash)
            msg += b'- merkle_root: %s\n' % hexlify(blk.merkle_root)
            msg += (b'- timestamp: %s\n'
                    % datetime.fromtimestamp(blk.timestamp)
                    .strftime('%Y-%m-%d %H:%M:%S').encode('utf-8'))
            msg += b'- diff: %i\n' % blk.diff
            msg += b'- nonce: %08x\n' % blk.nonce

            for tx in blk.txs:
                msg += b'--TX %s\n' % hexlify(tx.get_txid())
                for inp in tx.inputs:
                    if inp.txid == NO_HASH:
                        msg += (b'---- INP dummy 0 (%#x, %s...)\n'
                                % (inp.index, hexlify(inp.signature)[:32]))
                    else:
                        msg += (b'---- INP %s %i\n'
                                % (hexlify(inp.spent_output.pubkey),
                                   inp.spent_output.amount))
                for out in tx.outputs:
                    msg += (b'---- OUT %s %i\n'
                            % (hexlify(out.pubkey), out.amount))
            msg += b'\n'
        return msg


class Client:
    def __init__(self, host, port):
        self.blockchain = Blockchain()
        self.wallet = Wallet(self.blockchain, autoload=False)
        self.miner = Miner(self.blockchain, NO_PUBKEY)

        self.p2p = P2P(self.blockchain, self.miner, host, port)
        self.rpc = RPC(self.blockchain, self.miner, self.wallet, self.p2p)

    def main_loop(self):
        while True:
            self.p2p.handle_incoming_data()
            self.poll_miner()

            sleep(0.01)

    def poll_miner(self):
        mined_block = self.miner.get_mined_block()
        if mined_block is not None:
            self.blockchain.add_block(mined_block)
            self.p2p.broadcast_block(mined_block)


if __name__ == '__main__':
    logging.basicConfig(level=10)

    if len(argv) < 3:
        log.error('Usage: %s <host> <port>')

    cli = Client(argv[1], int(argv[2]))
    cli.main_loop()
