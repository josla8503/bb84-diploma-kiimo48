import secrets
import random

ENCODE_TABLE = {
    (0, 0): 0,
    (1, 0): 90,
    (0, 1): 45,
    (1, 1): 135,
}

DECODE_TABLE = {
    (0,   0): 0,
    (90,  0): 1,
    (45,  1): 0,
    (135, 1): 1,
}

POLARIZATIONS = [0, 90, 45, 135]

def text_to_bits(text: str) -> list[int]:
    bits = []
    for byte in text.encode('utf-8'):
        bits.extend(int(b) for b in f"{byte:08b}")
    return bits

def bits_to_text(bits: list[int]) -> str:
    byte_array = bytearray()
    for i in range(0, len(bits), 8):
        chunk = bits[i:i+8]
        if len(chunk) == 8:
            byte_val = int("".join(map(str, chunk)), 2)
            byte_array.append(byte_val)
    return byte_array.decode('utf-8', errors='replace')


def generate_alice_data(n: int) -> tuple[list[int], list[int]]:
    bits = [secrets.randbelow(2) for _ in range(n)]
    bases = [secrets.randbelow(2) for _ in range(n)]
    return bits, bases


def encode_qubits(bits: list[int], bases: list[int]) -> list[int]:
    return [ENCODE_TABLE[(b, basis)] for b, basis in zip(bits, bases)]


def measure_qubits(qubits: list[int], bob_bases: list[int]) -> list[int]:
    result = []
    for qubit, basis in zip(qubits, bob_bases):
        decoded = DECODE_TABLE.get((qubit, basis))
        if decoded is not None:
            result.append(decoded)
        else:
            result.append(secrets.randbelow(2))
    return result


def sift_key(
    alice_bases: list[int], bob_bases: list[int],
    alice_bits: list[int], bob_bits: list[int],
) -> tuple[list[int], list[int], list[int]]:
    alice_sifted, bob_sifted, indices = [], [], []
    for i, (ab, bb) in enumerate(zip(alice_bases, bob_bases)):
        if ab == bb:
            alice_sifted.append(alice_bits[i])
            bob_sifted.append(bob_bits[i])
            indices.append(i)
    return alice_sifted, bob_sifted, indices


def estimate_qber(
    alice_sifted: list[int], bob_sifted: list[int], sample_fraction: float = 0.25,
) -> tuple[float, list[int]]:
    n = len(alice_sifted)
    if n == 0: return 0.0, []

    k = max(1, int(n * sample_fraction))
    sample_indices = sorted(random.sample(range(n), k))
    errors = sum(alice_sifted[i] != bob_sifted[i] for i in sample_indices)
    return errors / k, sample_indices


def remove_sample(key: list[int], sample_mask: list[int]) -> list[int]:
    mask_set = set(sample_mask)
    return [b for i, b in enumerate(key) if i not in mask_set]