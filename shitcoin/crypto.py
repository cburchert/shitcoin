import hashlib
import ed25519


PUBKEY_LEN = 32
PRIVKEY_LEN = 64
SIG_LEN = 64
HASH_LEN = 32

NO_PUBKEY = b'\x00' * PUBKEY_LEN
NO_HASH = b'\x00' * HASH_LEN
NO_SIG = b'\x00' * SIG_LEN


def merkle_root(leaves):
    l = len(leaves)
    if l == 0:
        # Empty tree
        return h(b'')
    if l == 1:
        # a leaf
        return h(leaves[0])
    return h(merkle_root(leaves[:l//2]) + merkle_root(leaves[l//2:]))


def h(buf):
    m = hashlib.sha256()
    m2 = hashlib.sha256()
    m.update(buf)
    m2.update(m.digest())
    return m2.digest()


def generate_keypair():
    """ Generates (priv_key, pub_key) """
    priv_key, pub_key = ed25519.create_keypair()
    return (priv_key.to_bytes(), pub_key.to_bytes())


def sign(msg, priv_key):
    signer = ed25519.SigningKey(priv_key)
    return signer.sign(msg)


def verify_sig(msg, pub_key, sig):
    try:
        ed25519.VerifyingKey(pub_key).verify(sig, msg)
        return True
    except ed25519.BadSignatureError:
        return False
