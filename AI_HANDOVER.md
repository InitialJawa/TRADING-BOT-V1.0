# AI HANDOVER — TRADING BOT V1.0

## 1. TRADING BOT — STATUS

### Best 4 Live Tickers ✅
| Ticker | Strategy | Rp/hr | PF | DD | Status |
|--------|----------|-------|----|----|--------|
| **XAGUSDm** 👑 | D H1 Confluence | **Rp606k** | 2.54 | 10.6% | ✅ LIVE |
| **JP225m** 🚀 | G M15 Confidence | **Rp529k** | 2.50 | 6.5% | ✅ LIVE |
| ETHUSDm | D H1 Confluence | Rp468k | 2.05 | 11.5% | ✅ LIVE |
| BTCUSDTm | D H1 Confluence | Rp437k | 2.65 | 4.1% | ✅ LIVE |

### Live Bot
- `scripts/live_bot_4_ticker.py` — 4 ticker monitor + trailing stop + auto open posisi
- `scripts/run_live_bot.ps1 start|stop|log` — PowerShell runner
- Cek tiap 5 menit, manage trailing stop, buka posisi baru

### Constraints
- MT5 Exness-Trial6 (login 413889745) — live trading works
- XAUUSD PAKEM — untouched
- H1 data limited (2-3 days), forex pairs untradeable (low vol)

### MT5 EA Fix (2026-06-19)
**Root cause 0 trades:** `iMA(..., VOLUME_TICK)` di Strategy Tester balikin SMA harga close, bukan tick volume. Volume filter selalu false.

**Fix:** Hitung volume SMA manual pake loop `iVolume()`:
```cpp
double volMA = 0;
for (int vi = 1; vi <= 15; vi++) volMA += (double)iVolume(_Symbol, PERIOD_CURRENT, vi);
volMA /= 15.0;
```

**Compiled EAs:**
| EA | Path |
|----|------|
| `jp225m_g_m15.ex5` | `%APPDATA%\...\MQL5\Experts\` |
| `xagusdm_d_h1.ex5` | `%APPDATA%\...\MQL5\Experts\` |

**Test:** Buka MT5 → Ctrl+R (Strategy Tester) → pilih EA → Start. Debug `BAR>` tiap 50 bar + `OPEN BUY/SELL` di Journal.

---

## 2. AI COLLABORATION SYSTEM — JEMBATAN 2 OPENCODE AGENT

Dibangun supaya 2 AI (Dev + Reviewer) bisa saling ngobrol dan ngoding bareng secara otomatis.

### Arsitektur
```
Tab 1: python scripts/collab_watcher.py   (auto-pilot)
  ├── auto-trigger collab-dev (OpenCode)    → ngerjain task
  └── auto-trigger collab-reviewer (OpenCode) → review hasil
        ↓
data/agent_handoff.json  (jembatan komunikasi)
```

### File Structure
```
AGENTS.md                           ← instruksi untuk 2 AI
.opencode/agents/
  collab-dev/agent.json             ← Dev: ngerjain task coding
  collab-reviewer/agent.json        ← Reviewer: review hasil
  ai-risk-manager/agent.json        ← Risk manager (existing)
data/agent_handoff.json             ← task + result + feedback
scripts/collab_watcher.py           ← auto-loop watcher
src/agent_ipc.py                    ← file-based chat (opsional)
```

### Alur Kerja
```
Watcher detect "pending" / "feedback_given" assigned=dev
  → auto-run: opencode run --agent collab-dev
  → Dev baca handoff, coding, update result + status "review_needed"
  → Watcher detect perubahan
  → auto-run: opencode run --agent collab-reviewer
  → Reviewer baca result, cek file, kasih feedback
    → OK  → status "done"
    → Revisi → status "feedback_given", assigned "dev"
  → Loop sampe "done"
```

### Cara Pakai
```bash
# Tab 1 — watcher (auto-pilot, biarin jalan)
python scripts/collab_watcher.py

# Tab 2 — opsional, monitor aja
```

### Latest Task (Selesai)
| ID | Task | Status |
|----|------|--------|
| 1 | Fungsi `get_avg_drawdown_7d()` di state_manager | ✅ done |
| 2 | Live bot 4 ticker + PowerShell runner | ✅ done |

---

## 3. SELURUH KEY FILES
| Area | File |
|------|------|
| Entry point | `src/main.py` |
| State manager | `src/state_manager.py` |
| AI provider | `src/provider/opencode_cli.py` |
| Backtest engine | `scripts/backtest_multi_ticker.py` |
| Live bot | `scripts/live_bot_4_ticker.py` |
| Live runner | `scripts/run_live_bot.ps1` |
| Best configs | `config/best/best_4_configs.json` |
| Collab watcher | `scripts/collab_watcher.py` |
| Handoff | `data/agent_handoff.json` |
