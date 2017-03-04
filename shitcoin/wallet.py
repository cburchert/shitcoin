from binascii import hexlify, unhexlify
from collections import deque

from . import crypto
from .crypto import NO_HASH
from .exceptions import NotEnoughFunds
from .settings import WALLET_PATH, MIN_CONFIRMATIONS
from .transaction import Transaction, Input, Output


class Wallet:
    def __init__(self, blockchain, autoload=True):
        """ Creates a wallet.

        Args:
            key_list: list of tuples (priv_key, pub_key)
        """
        self.keys = []

        self.blockchain = blockchain

        # Cache our utxos to reduce the time searching for our money
        self.utxos = []  # known utxos
        self.current_block = None

        if autoload:
            self.load()

    def save(self):
        with open(WALLET_PATH, 'wb') as f:
            for priv_key, pub_key in self.keys:
                f.write(hexlify(priv_key))
                f.write(b':')
                f.write(hexlify(pub_key))
                f.write(b'\n')

    def load(self):
        try:
            with open(WALLET_PATH) as f:
                for line in f.readlines():
                    priv_key, pub_key = line.rstrip('\n').split(':')
                    self.keys.append((unhexlify(priv_key), unhexlify(pub_key)))
        except FileNotFoundError:
            # No wallet yet, create one
            self.new_address()
            self.save()

    def update_utxos(self):
        """ Update the utxos to reflect the current blockchain state.
        If some state is known, this will parse new transactions to update the
        state. Otherwise it will search through all known utxos for those where
        we know the private key.

        Args:
            blockchain(Blockchain): the blockchain instance to parse
        """
        if self.current_block == self.blockchain.head:
            # Nothing to do
            return

        # The pubkeys we will be looking for
        pubkeys = [key[1] for key in self.keys]

        if self.current_block is None:
            # No state yet, parse all utxos
            for txid, output_dict in self.blockchain.utxos.items():
                for index, output in output_dict.items():
                    if output.pubkey in pubkeys:
                        self.utxos.append({
                            'txid': txid,
                            'index': index,
                            'pubkey': output.pubkey,
                            'amount': output.amount,
                            'blockheight': output.block.get_height()
                        })
            self.current_block = self.blockchain.head
            return

        # We have some state, go to correct block

        # Collect the new blocks until we are at the same height
        # We can assume that the main blockchain only increases in lengh, so
        # the parsed chain is always shorter than the full blockchain
        blocks_to_apply = deque()
        cur = self.blockchain.head
        while cur.get_height() > self.current_block.get_height():
            blocks_to_apply.appendleft(cur)
            cur = cur.get_parent()

        # Walk up until we are at the same block (in case of reorg)
        while cur != self.current_block:
            # Save the block on the new side for later application
            blocks_to_apply.appendleft(cur)
            cur = cur.get_parent()

            # Revert the block on the old side of the fork
            for tx in self.current_block.txs:
                txid = tx.get_txid()
                # Remove all outputs with matching txids
                self.utxos = list(filter(lambda utxo: utxo['txid'] == txid,
                                         self.utxos))
                # Readd utxos spent by the inputs
                for inp in tx.inputs:
                    if inp.txid == NO_HASH:  # skip dummy inputs
                        continue
                    output = inp.spent_output
                    if output.pubkey in pubkeys:
                        self.utxos.append({
                            'txid': inp.txid,
                            'index': inp.index,
                            'pubkey': output.pubkey,
                            'amount': output.amount,
                            'blockheight': output.block.get_height()
                        })
            self.current_block = self.current_block.get_parent()

        # Apply the new blocks
        for blk in blocks_to_apply:
            for tx in blk.txs:
                # Remove referenced utxos
                for inp in tx.inputs:
                    self.utxos = list(filter(
                        lambda utxo: utxo['txid'] != inp.txid or
                        utxo['index'] != inp.index, self.utxos))
                # Add outputs with known pubkey
                for out in tx.outputs:
                    if out.pubkey in pubkeys:
                        self.utxos.append({
                            'txid': tx.get_txid(),
                            'index': tx.outputs.index(out),
                            'pubkey': out.pubkey,
                            'amount': out.amount,
                            'blockheight': out.block.get_height()
                        })
        self.current_block = blocks_to_apply[-1]

    def new_address(self):
        priv_key, pub_key = crypto.generate_keypair()
        self.keys.append((priv_key, pub_key))
        self.save()
        return pub_key

    def get_balance(self, address=None):
        self.update_utxos()

        balance = 0
        for utxo in self.utxos:
            if address is not None and utxo['pubkey'] != address:
                continue
            # Filter utxos with too few confirmations
            if (utxo['blockheight'] <=
                    self.current_block.get_height() - MIN_CONFIRMATIONS):
                balance += utxo['amount']
        return balance

    def get_addresses(self):
        """ Returns the list of addresses """
        return [key[1] for key in self.keys]

    def create_transaction(self, receivers, fee=100):
        """ Creates a transaction, which sends money to some receivers.

        Args:
            receivers(dict): dict pubkey -> amount of the receivers.
        """
        self.update_utxos()

        cur_balance = fee
        outputs = []
        for pubkey, amount in receivers.items():
            outputs.append(Output(amount, pubkey))
            cur_balance += amount

        # Pick some UTXOs, which combine to the correct value
        inputs = []
        inp_pubkeys = []
        for utxo in self.utxos:
            inputs.append(Input(utxo['txid'], utxo['index']))
            inp_pubkeys.append(utxo['pubkey'])
            cur_balance -= utxo['amount']
            if cur_balance <= 0:
                break

        if cur_balance > 0:
            # Not enough money
            raise NotEnoughFunds()

        # Add change
        outputs.append(Output(-cur_balance, self.new_address()))

        tx = Transaction()
        tx.inputs = inputs
        tx.outputs = outputs

        # Insert signatures
        txid = tx.get_txid()
        for i, inp in enumerate(tx.inputs):
            priv_key = next(k[0] for k in self.keys if k[1] == inp_pubkeys[i])
            inp.signature = crypto.sign(txid, priv_key)

        return tx
