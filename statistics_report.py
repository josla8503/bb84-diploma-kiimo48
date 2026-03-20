import csv
import math
import random
from itertools import product
from typing import Any

try:
    from prettytable import PrettyTable
    PT_AVAILABLE = True
except ImportError:
    PT_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

from bb84_protocol import (
    generate_alice_data, encode_qubits, measure_qubits,
    sift_key, estimate_qber, remove_sample,
)
from channel import transmit
from postprocessing import reconcile, privacy_amplification


def run_session(
    n:               int,
    p_err:           float,
    eve_enabled:     bool,
    p_intercept:     float,
    qber_threshold:  float = 0.11,
    sample_fraction: float = 0.25,
) -> dict[str, Any]:
    alice_bits, alice_bases = generate_alice_data(n)
    qubits = encode_qubits(alice_bits, alice_bases)

    received, eve_log = transmit(qubits, p_err, eve_enabled, p_intercept)

    bob_bases = [random.randint(0, 1) for _ in range(n)]
    bob_bits  = measure_qubits(received, bob_bases)

    alice_sifted, bob_sifted, match_idx = sift_key(
        alice_bases, bob_bases, alice_bits, bob_bits)

    n_sifted = len(alice_sifted)
    qber, sample_mask = estimate_qber(alice_sifted, bob_sifted, sample_fraction)

    eve_detected = qber > qber_threshold

    if eve_detected or n_sifted == 0:
        return {
            "n": n, "p_err": p_err, "eve_enabled": eve_enabled,
            "p_intercept": p_intercept, "n_sifted": n_sifted,
            "qber": qber, "eve_detected": eve_detected,
            "key_length": 0, "key_rate": 0.0,
            "alice_bases": alice_bases, "bob_bases": bob_bases,
            "sifted_alice": alice_sifted, "sifted_bob": bob_sifted,
            "match_indices": match_idx, "sample_mask": sample_mask,
            "secret_key": "",
        }

    a_work = remove_sample(alice_sifted, sample_mask)
    b_work = remove_sample(bob_sifted,   sample_mask)

    corrected_bob, leak_ec = reconcile(a_work, b_work, qber)
    secret_key = privacy_amplification(a_work, qber, leak_ec)

    return {
        "n": n, "p_err": p_err, "eve_enabled": eve_enabled,
        "p_intercept": p_intercept, "n_sifted": n_sifted,
        "qber": qber, "eve_detected": eve_detected,
        "key_length": len(secret_key), "key_rate": len(secret_key) / n,
        "alice_bases": alice_bases, "bob_bases": bob_bases,
        "sifted_alice": alice_sifted, "sifted_bob": bob_sifted,
        "match_indices": match_idx, "sample_mask": sample_mask,
        "secret_key": secret_key,
    }


def run_experiments(
    param_grid: dict[str, list],
    n_repeats:  int = 100,
) -> list[dict]:

    keys   = list(param_grid.keys())
    values = list(param_grid.values())
    grid   = list(product(*values))
    results = []

    total = len(grid)
    for gi, combo in enumerate(grid):
        params = dict(zip(keys, combo))
        if not params.get("eve_enabled", False):
            params["p_intercept"] = 0.0

        print(f"  [{gi+1}/{total}] {params} × {n_repeats} runs …", end=" ", flush=True)

        agg = {
            "qber": [], "key_length": [], "key_rate": [],
            "eve_detected": [], "n_sifted": [],
        }
        for _ in range(n_repeats):
            r = run_session(**params)
            for k in agg:
                agg[k].append(float(r[k]) if isinstance(r[k], bool) else r[k])

        row = {**params}
        for k, vals in agg.items():
            row[f"mean_{k}"] = sum(vals) / len(vals)

        results.append(row)
        print(f"QBER={row['mean_qber']:.2%}  key_rate={row['mean_key_rate']:.4f}")

    return results



COLUMNS = [
    ("n",                 "N"),
    ("p_err",             "p_err"),
    ("eve_enabled",       "Eve?"),
    ("p_intercept",       "p_int"),
    ("mean_qber",         "QBER"),
    ("mean_n_sifted",     "Sifted"),
    ("mean_key_length",   "Key len"),
    ("mean_key_rate",     "Key rate"),
    ("mean_eve_detected", "P(detect)"),
]


def build_table(results: list[dict], csv_path: str = "results.csv"):
    """Print a PrettyTable to stdout and export to CSV."""
    headers = [h for _, h in COLUMNS]

    if PT_AVAILABLE:
        tbl = PrettyTable(headers)
        tbl.float_format = ".4"
    else:
        print("  " + " | ".join(f"{h:>10}" for h in headers))
        print("  " + "-" * (13 * len(headers)))

    rows = []
    for r in results:
        row = []
        for key, _ in COLUMNS:
            val = r.get(key, "")
            if isinstance(val, float):
                row.append(f"{val:.4f}")
            elif isinstance(val, bool):
                row.append("Yes" if val else "No")
            else:
                row.append(str(val))
        rows.append(row)
        if PT_AVAILABLE:
            tbl.add_row(row)
        else:
            print("  " + " | ".join(f"{v:>10}" for v in row))

    if PT_AVAILABLE:
        print(tbl)

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"\nResults saved to {csv_path}")



def plot_key_rate(results: list[dict], save_path: str = "key_rate.png"):
    if not MPL_AVAILABLE:
        print("[plot_key_rate] matplotlib not available.")
        return

    p_intercepts = sorted(set(r.get("p_intercept", 0) for r in results))
    colours = plt.cm.viridis([i / max(1, len(p_intercepts) - 1)
                               for i in range(len(p_intercepts))])

    fig, ax = plt.subplots(figsize=(9, 5))
    for pi, colour in zip(p_intercepts, colours):
        subset = [r for r in results if r.get("p_intercept", 0) == pi]
        subset.sort(key=lambda r: r["p_err"])
        xs = [r["p_err"] * 100 for r in subset]
        ys = [r["mean_key_rate"] for r in subset]
        ax.plot(xs, ys, marker="o", label=f"p_int={pi:.1f}", color=colour)

    ax.set_xlabel("Channel noise p_err (%)")
    ax.set_ylabel("Key rate (bits per qubit)")
    ax.set_title("BB84 Key Generation Rate vs Channel Noise")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.show()
    print(f"Key-rate plot saved to {save_path}")


def _theoretical_detection(p_intercept: float) -> float:
    k = 50
    return 1 - (1 - 0.25 * p_intercept) ** k


def plot_eve_detection(results: list[dict], save_path: str = "eve_detection.png"):
    if not MPL_AVAILABLE:
        print("[plot_eve_detection] matplotlib not available.")
        return

    subset = [r for r in results if r.get("eve_enabled", False)]
    if not subset:
        print("[plot_eve_detection] No Eve-enabled results to plot.")
        return
    subset.sort(key=lambda r: r.get("p_intercept", 0))

    xs   = [r["p_intercept"] for r in subset]
    ys   = [r["mean_eve_detected"] for r in subset]
    theo = [_theoretical_detection(x) for x in xs]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(xs, ys,   "o-", label="Simulated", color="crimson")
    ax.plot(xs, theo, "s--", label="Theoretical", color="steelblue", alpha=0.7)
    ax.set_xlabel("Interception fraction p_intercept")
    ax.set_ylabel("P(Eve detected)")
    ax.set_title("BB84 Eavesdropper Detection Probability")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.show()
    print(f"Detection-probability plot saved to {save_path}")
