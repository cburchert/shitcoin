from functools import partial

from .utxoset import InvalidTransaction


class Mempool:
    def __init__(self, blockchain):
        self.blockchain = blockchain
        self.transactions = {}  # txid -> Transaction
        self.utxos = blockchain.utxos.copy()
        self.total_fees = 0

        self.blockchain.register_new_block_callback(
            partial(Mempool.incoming_block, self))

        # Callbacks
        self.new_tx_callbacks = []

    def add_transaction(self, transaction, inform_callbacks=True):
        txid = transaction.get_txid()

        if txid in self.transactions:
            return

        # Validate transaction
        try:
            temp_utxos = self.utxos.copy()
            fee = temp_utxos.apply_transaction(transaction, verify=True)
        except InvalidTransaction:
            return

        # Only mine transaction, which pay at least 10 fee
        if fee < 10:
            return

        # Transaction is valid, save it
        self.transactions[txid] = transaction
        self.total_fees += fee
        self.utxos.apply_transaction(transaction)

        # Inform callbacks
        if inform_callbacks:
            for func in self.new_tx_callbacks:
                func(transaction)

    def incoming_block(self, blk):
        # Remove all transactions from mempool, which are now in the blockchain
        for tx in blk.txs:
            try:
                self.transactions.pop(tx.get_txid())
            except KeyError:
                pass

        # Recreate the mempool utxo set
        txs = self.transactions
        self.transactions = {}
        self.utxos = self.blockchain.utxos.copy()
        self.total_fees = 0

        # Readd all transactions, which can still be applied
        # TODO: This ignores the order, so some might get excluded due to wrong
        # ordering
        for tx in txs.values():
            self.add_transaction(tx, False)

    def register_new_tx_callback(self, func):
        self.new_tx_callbacks.append(func)
