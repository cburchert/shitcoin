from os import path

GENESIS_PREVHASH = b'\xde\xad\xbe\xef' * 8
GENESIS_TIME = 0

BLOCK_TIME = 5.0  # seconds
DIFF_PERIOD_LEN = 10  # Adjust diff every x blocks

# Total money supply = REWARD_HALVING_LEN * INITIAL_REWARD * 2
REWARD_HALVING_LEN = 1000  # Half block reward every x blocks
INITIAL_REWARD = 1000  # Block reward at the beginning

DATA_FOLDER = 'data'
WALLET_PATH = path.join(DATA_FOLDER, 'wallet')

# Wallet settings
MIN_CONFIRMATIONS = 10
