import sys
import os
import json
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.state_manager import StateManager
from src.audit.system_audit import SystemAudit
from src.audit.risk_audit import RiskAudit
from src.audit.backtest_audit import BacktestAudit
from src.context_builder import ContextBuilder
from src.decision_parser import DecisionParser
from src.override_handler import OverrideHandler

random.seed(42)

MODAL_AWAL = 5_000_000  # IDR
BIAYA_BULANAN = 50_000   # biaya VPS dll


def simulasi_bulan(bulan_ke, modal_sekarang, return_pct):
    laba_rugi = modal_sekarang * (return_pct / 100)
    bersih = laba_rugi - BIAYA_BULANAN
    return round(bersih, 2)


def simulasikan(judul, jumlah_bulan, returns_bulanan):
    print("\n" + "=" * 70)
    print(f" {judul}")
    print(f" Modal Awal: Rp{MODAL_AWAL:,.0f}")
    print("=" * 70)

    state = StateManager(f"data/demo_{jumlah_bulan}m.db")
    parser = DecisionParser(f"data/demo_{jumlah_bulan}m_errors.log")
    handler = OverrideHandler(state, f"data/demo_{jumlah_bulan}m_decisions.log")

    modal = MODAL_AWAL
    total_laba = 0
    total_rugi = 0
    bulan_negatif = 0
    drawdown_tertinggi = 0
    puncak_tertinggi = modal

    for i in range(jumlah_bulan):
        ret = returns_bulanan[i]
        hasil = simulasi_bulan(i + 1, modal, ret)
        modal += hasil

        if hasil > 0:
            total_laba += hasil
        else:
            total_rugi += abs(hasil)
            bulan_negatif += 1

        if modal > puncak_tertinggi:
            puncak_tertinggi = modal
        dd_saat_ini = round((puncak_tertinggi - modal) / puncak_tertinggi * 100, 2)
        if dd_saat_ini > drawdown_tertinggi:
            drawdown_tertinggi = dd_saat_ini

        rolling_sharpe = round((sum(returns_bulanan[max(0, i-6):i+1]) / max(len(returns_bulanan[max(0, i-6):i+1]), 1)) / max(abs(min(returns_bulanan[max(0, i-6):i+1])), 0.01), 2)

        state.upsert_metric("portfolio_drawdown", dd_saat_ini)
        state.upsert_metric("rolling_sharpe_7d", rolling_sharpe)
        state.upsert_metric("last_heartbeat", (datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 2))).isoformat())
        state.upsert_metric(f"modal_bulan_{i+1}", round(modal, 2))
        if i % 3 == 0:
            bt_result = "PASS" if ret >= 0 else "FAILED"
            state.log_backtest("adaptive", bt_result, {"month": i+1, "return": ret})
        if ret < -3:
            state.log_error("strategy", f"Large negative return: {ret}% in month {i+1}")

        print(f"\n  Bulan {i+1:2d} | Return: {ret:+.1f}% | Hasil: Rp{hasil:+,.0f} | Modal: Rp{modal:,.0f} | DD: {dd_saat_ini:.1f}% | Sharpe: {rolling_sharpe}")

    # Final audits
    system_audit = SystemAudit(state)
    risk_audit = RiskAudit(state)
    backtest_audit = BacktestAudit(state)
    context_builder = ContextBuilder(state, risk_audit, system_audit, backtest_audit)

    print(f"")
    print(f"  AUDIT AKHIR:")
    sa = system_audit.run_all()
    ra = risk_audit.run_all()
    ba = backtest_audit.run_all()
    print(f"  +- System: VPS={sa['vps_health']['status']}, MT5={sa['mt5_connectivity']['status']}")
    print(f"  +- Risk: Drawdown={ra['drawdown']['value']}% [{ra['drawdown']['level']}], Sharpe={ra['sharpe']['value']} [{ra['sharpe']['level']}]")
    print(f"  +- Backtest: {ba['status']} [{ba['level']}]")

    ctx = context_builder.build()
    prompt = context_builder.build_prompt()
    print(f"\n  CONTEXT KE AI:")
    for k, v in ctx.items():
        print(f"    {k}: {v}")

    print(f"\n  PROMPT AI (length: {len(prompt)} chars):")
    print(f"    {prompt[:400]}...")

    roi = round((modal - MODAL_AWAL) / MODAL_AWAL * 100, 2)
    print(f"")
    print(f"  RINGKASAN {jumlah_bulan} BULAN:")
    print(f"  +- Modal Akhir:  Rp{modal:,.0f}")
    print(f"  +- Total Laba:   Rp{total_laba:,.0f}")
    print(f"  +- Total Rugi:   Rp{total_rugi:,.0f}")
    print(f"  +- ROI:          {roi:+.2f}%")
    print(f"  +- Drawdown Max: {drawdown_tertinggi:.1f}%")
    print(f"  +- Bulan Untung: {jumlah_bulan - bulan_negatif}x")
    print(f"  +- Bulan Rugi:   {bulan_negatif}x")
    print(f"  +- Rata-rata/bln: Rp{round((modal - MODAL_AWAL) / jumlah_bulan):,.0f}/bulan")
    print(f"  {'=' * 50}")

    # Simulasi AI decision
    print(f"\n  DECISION AI (SIMULASI):")
    if ra["drawdown"]["level"] == "CRITICAL":
        sim = f'{{"action": "reduce_lot", "target": "xauusdm", "value": 0.3, "reason": "Drawdown {ra["drawdown"]["value"]}% critical"}}'
        dec = parser.parse(sim)
        if dec:
            res = handler.execute(dec)
            print(f"  +- Action: reduce_lot -> {res['status']}")
            print(f"  +- Message: {res['message']}")
    elif ra["drawdown"]["level"] == "WARNING":
        print(f"  +- Action: alert_only -> WARNING: Drawdown {ra['drawdown']['value']}% approaching limit")
    elif ba["level"] == "FAILED":
        sim = f'{{"action": "pause_strategy", "target": "adaptive", "value": null, "reason": "Backtest FAILED"}}'
        dec = parser.parse(sim)
        if dec:
            res = handler.execute(dec)
            print(f"  +- Action: pause_strategy -> {res['status']}")
            print(f"  +- Message: {res['message']}")
    else:
        print(f"  +- Action: alert_only -> All systems normal")

    return modal


# --- SKENARIO RETURN PER BULAN ---

# 8 Bulan: aggressive dengan 2 krisis
returns_8bln = [
    12.5,  # bulan 1: bull
    15.2,  # bulan 2: bull
    -5.8,  # bulan 3: koreksi
    18.7,  # bulan 4: rally besar
    -14.2, # bulan 5: KRISIS - drawdown besar
    9.5,   # bulan 6: rebound
    22.3,  # bulan 7: bull besar
    -11.8, # bulan 8: koreksi akhir
]

# 4 Bulan: aggressive
returns_4bln = [
    14.2,
    -8.5,
    19.8,
    -6.2,
]

# 2 Bulan: aggressive short
returns_2bln = [
    16.5,
    -9.8,
]

hasil_8bln = simulasikan("SIMULASI 8 BULAN", 8, returns_8bln)
hasil_4bln = simulasikan("SIMULASI 4 BULAN", 4, returns_4bln)
hasil_2bln = simulasikan("SIMULASI 2 BULAN", 2, returns_2bln)

print("\n" + "=" * 70)
print("                        KESIMPULAN AKHIR")
print("=" * 70)
print(f"  Modal Awal:       Rp{MODAL_AWAL:,.0f}")
print(f"  Hasil 8 bulan:    Rp{hasil_8bln:,.0f}  ({round((hasil_8bln-MODAL_AWAL)/MODAL_AWAL*100, 2):+.2f}%)")
print(f"  Hasil 4 bulan:    Rp{hasil_4bln:,.0f}  ({round((hasil_4bln-MODAL_AWAL)/MODAL_AWAL*100, 2):+.2f}%)")
print(f"  Hasil 2 bulan:    Rp{hasil_2bln:,.0f}  ({round((hasil_2bln-MODAL_AWAL)/MODAL_AWAL*100, 2):+.2f}%)")
print("=" * 70)
