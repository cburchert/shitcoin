class InvalidTransaction(Exception):
    pass


class UTXONotFound(InvalidTransaction):
    pass


class BadSignature(InvalidTransaction):
    pass


class InvalidBlock(Exception):
    pass


class NotEnoughFunds(Exception):
    pass
