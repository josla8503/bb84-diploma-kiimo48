import argparse
import random
import traceback

from bb84_protocol import (
    generate_alice_data, encode_qubits, measure_qubits,
    sift_key, estimate_qber, remove_sample, text_to_bits, bits_to_text
)
from channel import transmit
from postprocessing import reconcile, privacy_amplification

QBER_THRESHOLD   = 0.11
SAMPLE_FRACTION  = 0.25

def run_demo(args):
    eve_enabled  = args.eve
    p_intercept  = args.p_intercept if eve_enabled else 0.0
    p_err        = args.p_err

    req_len = 0
    if args.message:
        msg_bits = text_to_bits(args.message)
        req_len = len(msg_bits)
        multiplier = 10 if eve_enabled else 5
        n = max(args.n, req_len * multiplier)
    else:
        n = args.n

    print("Протокол Квантового Распределения Ключей BB84")
    print(f"Кубитов (N) = {n} | Шум (p_err) = {p_err:.2%} | Ева = {'Да' if eve_enabled else 'Нет'}")
    if args.message:
        print(f"Передаваемое сообщение: '{args.message}'")

    viz = False
    viz_fns = {}
    if not args.no_viz:
        try:
            import visualizer_dpg as _viz_mod
            if _viz_mod.DPG_AVAILABLE:
                viz = _viz_mod.init_display(eve_present=eve_enabled)
                if viz:
                    viz_fns = {
                        "tx":    _viz_mod.draw_transmission_step,
                        "sift":  _viz_mod.draw_sifting_step,
                        "qber":  _viz_mod.draw_qber_estimation,
                        "otp":   _viz_mod.draw_otp_animation,
                        "final": _viz_mod.draw_final_result,
                        "close": _viz_mod.close_display,
                    }
        except Exception as e:
            print("\nОШИБКА ЗАПУСКА ИНТЕРФЕЙСА")
            print(f"{e}")
            traceback.print_exc()
            viz = False

    alice_bits, alice_bases = generate_alice_data(n)
    qubits = encode_qubits(alice_bits, alice_bases)

    received, eve_log = transmit(qubits, p_err, eve_enabled, p_intercept)
    print(f"Отправлено {n} кубитов. Ева перехватила {eve_log.n_intercepted}.")

    bob_bases = [random.randint(0, 1) for _ in range(n)]
    bob_bits  = measure_qubits(received, bob_bases)

    if viz:
        eve_set = set(eve_log.intercepted_indices)
        for i in range(n):
            if not _viz_mod.running():
                viz = False; break
            eve_int = i in eve_set
            ei = eve_log.intercepted_indices.index(i) if eve_int else None
            viz_fns["tx"]({
                "index": i, "alice_bit": alice_bits[i], "alice_basis": alice_bases[i],
                "qubit": qubits[i], "eve_intercepted": eve_int,
                "eve_basis": eve_log.eve_bases[ei] if eve_int and ei is not None else None,
                "eve_bit": eve_log.eve_bits[ei] if eve_int and ei is not None else None,
                "bob_basis": bob_bases[i], "bob_bit": bob_bits[i],
            }, eve_present=eve_enabled)

    alice_sifted, bob_sifted, match_idx = sift_key(alice_bases, bob_bases, alice_bits, bob_bits)
    if viz: viz_fns["sift"](alice_bases, bob_bases, match_idx)

    qber, sample_mask = estimate_qber(alice_sifted, bob_sifted, SAMPLE_FRACTION)
    print(f"Уровень ошибок (QBER): {qber:.2%} (порог {QBER_THRESHOLD:.0%})")
    if viz: viz_fns["qber"](alice_sifted, bob_sifted, sample_mask, qber, QBER_THRESHOLD)

    eve_detected = qber > QBER_THRESHOLD
    if eve_detected:
        print("\nОБНАРУЖЕН ПЕРЕХВАТ (ЕВА)")
        print("Продолжаем выполнение только для демонстрационных целей\n")

    a_work = remove_sample(alice_sifted, sample_mask)
    b_work = remove_sample(bob_sifted,   sample_mask)
    corrected_bob, leak_ec = reconcile(a_work, b_work, qber)
    
    secret_key = privacy_amplification(a_work, qber, leak_ec, educational_mode=True, min_len=req_len)
    
    print(f"Финальный защищенный ключ: {len(secret_key)} бит")

    info = {"n": n, "qber": qber, "eve_detected": eve_detected, "key_rate": len(secret_key)/n if n>0 else 0}

    if args.message:
        if len(secret_key) < len(msg_bits):
            print("\nОШИБКА: Сгенерированный квантовый ключ слишком короткий для этого текста!")
        else:
            print("ОДНОРАЗОВЫЙ БЛОКНОТ (OTP)")

            pad = [int(b) for b in secret_key[:len(msg_bits)]]

            cipher_bits = [m ^ p for m, p in zip(msg_bits, pad)]
            cipher_hex = "".join(f"{int(''.join(map(str, cipher_bits[i:i+4])), 2):x}" for i in range(0, len(cipher_bits), 4))
            
            bob_dec_bits = [c ^ p for c, p in zip(cipher_bits, pad)]
            bob_text = bits_to_text(bob_dec_bits)

            eve_fake_pad = [random.randint(0,1) for _ in range(len(msg_bits))]
            eve_dec_bits = [c ^ p for c, p in zip(cipher_bits, eve_fake_pad)]
            eve_text = bits_to_text(eve_dec_bits)

            print(f"Алиса отправила : {args.message}")
            print(f"Шифртекст       : 0x{cipher_hex.upper()}")
            print(f"Боб расшифровал : {bob_text}")
            print(f"Ева расшифровала: {eve_text}")
            
            info.update({
                "alice_text": args.message, "bob_text": bob_text, "eve_text": eve_text, 
                "cipher_hex": cipher_hex, "msg_bits": msg_bits, "pad": pad, 
                "cipher_bits": cipher_bits, "bob_dec_bits": bob_dec_bits, 
                "eve_fake_pad": eve_fake_pad, "eve_dec_bits": eve_dec_bits
            })

    if viz:
        if args.message and len(secret_key) >= req_len:
            viz_fns["otp"](info)
        else:
            viz_fns["final"](secret_key, info)
        viz_fns["close"]()

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    p_demo = sub.add_parser("demo")
    p_demo.add_argument("--message", type=str, default=None)
    p_demo.add_argument("--n", type=int, default=200)
    p_demo.add_argument("--p_err", type=float, default=0.01)
    p_demo.add_argument("--eve", action="store_true")
    p_demo.add_argument("--p_intercept", type=float, default=1.0)
    p_demo.add_argument("--no_viz", action="store_true")
    args = parser.parse_args()
    if args.mode == "demo": run_demo(args)

if __name__ == "__main__":
    main()