import argparse
import random
import traceback
import sys

from bb84_protocol import (
    generate_alice_data, encode_qubits, measure_qubits,
    sift_key, estimate_qber, remove_sample, text_to_bits, bits_to_text
)
from channel import transmit
from postprocessing import reconcile, privacy_amplification

QBER_THRESHOLD   = 0.11
SAMPLE_FRACTION  = 0.25

class MockArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def run_demo(args):
    eve_enabled  = args.eve
    p_intercept  = args.p_intercept if eve_enabled else 0.0
    p_err        = args.p_err
    attack_type  = getattr(args, 'attack', 'ir')

    req_len = 0
    if args.message:
        msg_bits = text_to_bits(args.message)
        req_len = len(msg_bits)
        multiplier = 10 if eve_enabled else 5
        n = max(args.n, req_len * multiplier)
    else:
        n = args.n

    print("Протокол Квантового Распределения Ключей BB84")
    print(f"Кубитов (N) = {n} | Шум (p_err) = {p_err:.2%} | Ева = {'Да' if eve_enabled else 'Нет'} ({attack_type.upper()})")

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
            viz = False

    alice_bits, alice_bases = generate_alice_data(n)
    qubits = encode_qubits(alice_bits, alice_bases)

    received, eve_log = transmit(qubits, p_err, eve_enabled, p_intercept, attack_type)
    print(f"Отправлено {n} кубитов. Ева перехватила {eve_log.n_intercepted}.")

    bob_bases = [random.randint(0, 1) for _ in range(n)]
    bob_bits  = measure_qubits(received, bob_bases)

    if viz:
        eve_set = set(eve_log.intercepted_indices)
        for i in range(n):
            if not _viz_mod.running():
                viz = False; break
            eve_int = i in eve_set
            
            eve_b = alice_bases[i] if (eve_int and attack_type == "pns") else None
            eve_bit = alice_bits[i] if (eve_int and attack_type == "pns") else None
            
            if attack_type == "ir" and eve_int:
                ei = eve_log.intercepted_indices.index(i)
                eve_b = eve_log.eve_bases[ei]
                eve_bit = eve_log.eve_bits[ei]

            viz_fns["tx"]({
                "index": i, "alice_bit": alice_bits[i], "alice_basis": alice_bases[i],
                "qubit": qubits[i], "eve_intercepted": eve_int,
                "eve_basis": eve_b, "eve_bit": eve_bit,
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
    
    eve_pre_pa = []
    eve_set = set(eve_log.intercepted_indices)
    sample_set = set(sample_mask)
    
    for i_sift, orig_idx in enumerate(match_idx):
        if i_sift in sample_set:
            continue
        if orig_idx in eve_set:
            if attack_type == "pns":
                eve_pre_pa.append(alice_bits[orig_idx])
            else:
                ei = eve_log.intercepted_indices.index(orig_idx)
                eve_pre_pa.append(eve_log.eve_bits[ei])
        else:
            eve_pre_pa.append(random.randint(0, 1))

    secret_key = privacy_amplification(a_work, qber, leak_ec, educational_mode=True, min_len=req_len)
    eve_key = privacy_amplification(eve_pre_pa, qber, leak_ec, educational_mode=True, min_len=req_len)
    
    print(f"Финальный защищенный ключ: {len(secret_key)} бит")

    info = {"n": n, "qber": qber, "eve_detected": eve_detected, "key_rate": len(secret_key)/n if n>0 else 0}

    if args.message:
        if len(secret_key) < len(msg_bits):
            print("\nОШИБКА: Сгенерированный квантовый ключ слишком короткий для этого текста!")
        else:
            pad = [int(b) for b in secret_key[:len(msg_bits)]]

            cipher_bits = [m ^ p for m, p in zip(msg_bits, pad)]
            cipher_hex = "".join(f"{int(''.join(map(str, cipher_bits[i:i+4])), 2):x}" for i in range(0, len(cipher_bits), 4))
            
            bob_dec_bits = [c ^ p for c, p in zip(cipher_bits, pad)]
            bob_text = bits_to_text(bob_dec_bits)

            if len(eve_key) >= len(msg_bits):
                eve_pad = [int(b) for b in eve_key[:len(msg_bits)]]
            else:
                eve_pad = [random.randint(0,1) for _ in range(len(msg_bits))]
                
            eve_dec_bits = [c ^ p for c, p in zip(cipher_bits, eve_pad)]
            eve_text = bits_to_text(eve_dec_bits)

            print(f"Алиса отправила : {args.message}")
            print(f"Шифртекст       : 0x{cipher_hex.upper()}")
            print(f"Боб расшифровал : {bob_text}")
            print(f"Ева расшифровала: {eve_text}")
            
            info.update({
                "alice_text": args.message, "bob_text": bob_text, "eve_text": eve_text, 
                "cipher_hex": cipher_hex, "msg_bits": msg_bits, "pad": pad, 
                "cipher_bits": cipher_bits, "bob_dec_bits": bob_dec_bits, 
                "eve_fake_pad": eve_pad, "eve_dec_bits": eve_dec_bits
            })

    if viz:
        if args.message and len(secret_key) >= req_len:
            viz_fns["otp"](info)
        else:
            viz_fns["final"](secret_key, info)
        viz_fns["close"]()

def main():
    if len(sys.argv) == 1:
        try:
            import dearpygui.dearpygui as dpg
            HAS_DPG = True
        except ImportError:
            HAS_DPG = False

        if not HAS_DPG:
            sys.exit(1)

        dpg.create_context()
        dpg.create_viewport(title="BB84", width=640, height=830, resizable=False)
        dpg.setup_dearpygui()

        try:
            import visualizer_dpg
            visualizer_dpg.load_cyrillic_font()
            visualizer_dpg._context_created = True 
        except Exception:
            pass

        params = {"launched": False}

        def update_dynamic_n(sender, app_data, user_data):
            msg = dpg.get_value("msg_input")
            base_n = dpg.get_value("n_input")
            eve = dpg.get_value("eve_checkbox")
            
            msg_bits_len = len(msg.encode('utf-8')) * 8
            
            if msg_bits_len > 0:
                multiplier = 10 if eve else 5
                actual_n = max(base_n, msg_bits_len * multiplier)
                
                info = (f"Текст занимает {msg_bits_len} бит. Из-за потерь в протоколе (сверка базисов, QBER,\n"
                        f"усиление секретности), итоговое количество кубитов растянуто до N = {actual_n}.")
                color = (255, 158, 100)
            else:
                info = f"Итоговое количество кубитов: N = {base_n}"
                color = (166, 227, 161)
                
            dpg.set_value("actual_n_display", info)
            dpg.configure_item("actual_n_display", color=color)

        def toggle_eve(sender, app_data):
            is_enabled = dpg.get_value(sender)
            dpg.configure_item("pintercept_input", enabled=is_enabled)
            dpg.configure_item("attack_combo", enabled=is_enabled)
            update_dynamic_n(sender, app_data, None)

        def on_launch(sender, app_data):
            params["message"] = dpg.get_value("msg_input")
            params["n"] = dpg.get_value("n_input")
            params["p_err"] = dpg.get_value("perr_input")
            params["eve"] = dpg.get_value("eve_checkbox")
            params["p_intercept"] = dpg.get_value("pintercept_input")
            attack_val = dpg.get_value("attack_combo")
            params["attack"] = "pns" if "PNS" in attack_val else "ir"
            params["no_viz"] = not dpg.get_value("viz_checkbox")
            params["launched"] = True

        with dpg.theme() as launcher_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 25, 25)
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (22, 24, 34))
        
        with dpg.theme() as btn_theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, (94, 161, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (114, 181, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (74, 141, 235))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (15, 17, 24))

        # Окно без строгих размеров (они будут игнорироваться)
        with dpg.window(tag="launcher_win", no_collapse=True, no_close=True, no_move=True, no_title_bar=True):
            dpg.add_text("КВАНТОВОЕ РАСПРЕДЕЛЕНИЕ КЛЮЧЕЙ", color=(94, 161, 255))
            dpg.add_text("Настройка симуляции протокола BB84", color=(110, 115, 130))
            dpg.add_separator()
            dpg.add_spacer(height=10)

            dpg.add_text("Сообщение для передачи (OTP):", color=(166, 227, 161))
            dpg.add_input_text(tag="msg_input", width=-1, callback=update_dynamic_n)
            dpg.add_text("Ключ будет использован для шифрования этого текста (Одноразовый Блокнот).", color=(110, 115, 130), wrap=590)
            dpg.add_spacer(height=10)

            dpg.add_text("Базовое количество кубитов (N):", color=(166, 227, 161))
            dpg.add_input_int(tag="n_input", default_value=200, width=150, min_value=10, min_clamped=True, callback=update_dynamic_n)
            dpg.add_text("Итоговое количество кубитов: N = 200", tag="actual_n_display", color=(166, 227, 161))
            dpg.add_spacer(height=15)

            dpg.add_text("Естественный шум квантового канала (p_err):", color=(94, 161, 255))
            dpg.add_slider_float(tag="perr_input", default_value=0.00, max_value=0.5, width=-1, format="%.3f")
            dpg.add_text("Имитирует несовершенство оптоволокна. Если общий уровень ошибок (QBER)\n"
                         "превысит 11%, протокол прервется, посчитав канал скомпрометированным.", color=(110, 115, 130), wrap=590)
            dpg.add_spacer(height=15)

            dpg.add_text("Перехватчик (Ева)", color=(243, 139, 168))
            dpg.add_separator()
            dpg.add_spacer(height=5)
            dpg.add_checkbox(label=" Активировать присутствие Евы", tag="eve_checkbox", callback=toggle_eve)
            
            dpg.add_spacer(height=5)
            dpg.add_text("Тип квантовой атаки:")
            dpg.add_combo(
                items=["Intercept-Resend (Обнаруживаемая)", "PNS - Разделение числа фотонов (Скрытая)"],
                default_value="PNS - Разделение числа фотонов (Скрытая)",
                tag="attack_combo", width=-1, enabled=False
            )
            dpg.add_text("Intercept-Resend: Ева измеряет кубит наугад. Вносит QBER, быстро себя выдает.\n"
                         "PNS: Из-за несовершенства лазеров Алисы летят сдвоенные фотоны. Ева ворует\n"
                         "один, не меняя второй, и позже измеряет его идеально (QBER=0).", color=(110, 115, 130), wrap=590)
            
            dpg.add_spacer(height=5)
            dpg.add_text("Интенсивность перехвата (p_intercept):")
            dpg.add_slider_float(tag="pintercept_input", default_value=1.0, max_value=1.0, width=-1, format="%.2f")
            dpg.configure_item("pintercept_input", enabled=False)

            dpg.add_spacer(height=10)
            dpg.add_text("Интерфейс", color=(255, 158, 100))
            dpg.add_separator()
            dpg.add_spacer(height=5)
            dpg.add_checkbox(label=" Включить пошаговый визуализатор (DPG)", default_value=True, tag="viz_checkbox")

            dpg.add_spacer(height=15)
            btn = dpg.add_button(label="НАЧАТЬ СИМУЛЯЦИЮ", width=-1, height=50, callback=on_launch)
            dpg.bind_item_theme(btn, btn_theme)

        dpg.bind_item_theme("launcher_win", launcher_theme)
        
        dpg.set_primary_window("launcher_win", True)
        
        update_dynamic_n(None, None, None)
        dpg.show_viewport()

        while dpg.is_dearpygui_running() and not params["launched"]:
            dpg.render_dearpygui_frame()

        if not params["launched"]:
            dpg.destroy_context()
            sys.exit(0)

        dpg.delete_item("launcher_win")

        demo_args = MockArgs(
            mode="demo",
            message=params["message"] if params["message"].strip() else None,
            n=params["n"],
            p_err=params["p_err"],
            eve=params["eve"],
            p_intercept=params["p_intercept"],
            attack=params["attack"],
            no_viz=params["no_viz"]
        )
        run_demo(demo_args)

    else:
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="mode", required=True)
        p_demo = sub.add_parser("demo")
        p_demo.add_argument("--message", type=str, default=None)
        p_demo.add_argument("--n", type=int, default=200)
        p_demo.add_argument("--p_err", type=float, default=0.01)
        p_demo.add_argument("--eve", action="store_true")
        p_demo.add_argument("--attack", type=str, choices=["ir", "pns"], default="ir")
        p_demo.add_argument("--p_intercept", type=float, default=1.0)
        p_demo.add_argument("--no_viz", action="store_true")
        args = parser.parse_args()
        
        if args.mode == "demo":
            run_demo(args)

if __name__ == "__main__":
    main()