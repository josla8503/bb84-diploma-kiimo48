import math
import hashlib
import random


def _binary_entropy(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def _parity(block: list[int]) -> int:
    result = 0
    for b in block:
        result ^= b
    return result


def _bisect_correct(alice_block: list[int], bob_block: list[int]) -> list[int]:
    bob = bob_block[:]
    lo, hi = 0, len(bob)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _parity(alice_block[lo:mid]) != _parity(bob[lo:mid]):
            hi = mid
        else:
            lo = mid
    if lo < len(bob):
        bob[lo] ^= 1
    return bob


def reconcile(
    alice_key: list[int],
    bob_key:   list[int],
    qber:      float,
    n_rounds:  int = 4,
) -> tuple[list[int], float]:
    n = len(alice_key)
    if n == 0:
        return [], 0.0

    if n < 32:
        n_rounds = 1
    elif n < 128:
        n_rounds = 2

    if qber <= 0:
        block_size = max(4, n // 2)
    else:
        block_size = max(4, min(n, int(1.0 / qber)))

    bob = bob_key[:]
    parity_bits_revealed = 0

    for round_idx in range(n_rounds):
        indices = list(range(n))
        random.seed(round_idx * 12345)
        random.shuffle(indices)

        for start in range(0, n, block_size):
            idx_block = indices[start:start + block_size]
            a_block = [alice_key[i] for i in idx_block]
            b_block = [bob[i] for i in idx_block]
            parity_bits_revealed += 1

            if _parity(a_block) != _parity(b_block):
                corrected = _bisect_correct(a_block, b_block)
                for j, i in enumerate(idx_block):
                    bob[i] = corrected[j]
                parity_bits_revealed += int(math.log2(len(idx_block)) + 1)

    leak_ec = min(1.0, parity_bits_revealed / n) if n > 0 else 0.0
    return bob, leak_ec


def privacy_amplification(
    key:     list[int],
    qber:    float,
    leak_ec: float,
    educational_mode: bool = False,
    min_len: int = 0
) -> str:
    n = len(key)
    if n == 0 and not educational_mode:
        return ""

    h_qber = _binary_entropy(qber)
    
    if educational_mode:
        l = max(min_len, int(n * (1.0 - h_qber - leak_ec)))
    else:
        l = max(0, int(n * (1.0 - h_qber - leak_ec)))

    if l == 0:
        return ""

    key_bytes = bytearray()
    for i in range(0, n, 8):
        byte = 0
        for bit in key[i:i + 8]:
            byte = (byte << 1) | bit
        key_bytes.append(byte)

    bits_needed = l
    result_bits = ""
    salt = 0
    while bits_needed > 0:
        h = hashlib.sha256(key_bytes + salt.to_bytes(4, 'big')).digest()
        for byte in h:
            for shift in range(7, -1, -1):
                result_bits += str((byte >> shift) & 1)
                bits_needed -= 1
                if bits_needed <= 0:
                    break
            if bits_needed <= 0:
                break
        salt += 1

    return result_bits[:l]