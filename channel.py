import secrets
import random
from dataclasses import dataclass, field

from bb84_protocol import ENCODE_TABLE, DECODE_TABLE, POLARIZATIONS


@dataclass
class EveLog:
    intercepted_indices: list = field(default_factory=list)
    eve_bases:           list = field(default_factory=list)
    eve_bits:            list = field(default_factory=list)
    resent_qubits:       list = field(default_factory=list)
    n_intercepted:       int  = 0


def _basis_of(qubit: int) -> int:
    return 0 if qubit in (0, 90) else 1


def _decode(qubit: int, basis: int) -> int:
    bit = DECODE_TABLE.get((qubit, basis))
    if bit is None:
        bit = secrets.randbelow(2)
    return bit


def eve_intercept(qubit: int) -> tuple[int, int, int]:
    eve_basis = secrets.randbelow(2)
    eve_bit   = _decode(qubit, eve_basis)
    resent    = ENCODE_TABLE[(eve_bit, eve_basis)]
    return resent, eve_basis, eve_bit


def eve_mitm(qubits: list[int], alice_bases_guess: list[int]) -> list[int]:
    result = []
    for qubit, basis_guess in zip(qubits, alice_bases_guess):
        bit = _decode(qubit, basis_guess)
        result.append(ENCODE_TABLE[(bit, basis_guess)])
    return result


def transmit(
    qubits:       list[int],
    p_err:        float,
    eve_enabled:  bool,
    p_intercept:  float,
) -> tuple[list[int], EveLog]:
    received = []
    log = EveLog()

    for i, qubit in enumerate(qubits):
        current = qubit

        if eve_enabled and random.random() < p_intercept:
            resent, eb, ebit = eve_intercept(current)
            log.intercepted_indices.append(i)
            log.eve_bases.append(eb)
            log.eve_bits.append(ebit)
            log.resent_qubits.append(resent)
            log.n_intercepted += 1
            current = resent

        if p_err > 0 and random.random() < p_err:
            others = [p for p in POLARIZATIONS if p != current]
            current = random.choice(others)

        received.append(current)

    return received, log
