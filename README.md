# Trading Bot V1.0 — AI Risk & Operations Manager

Sistem trading otomatis dengan arsitektur AI-driven untuk audit, monitoring, dan risk management. Integrasi dengan OpenCode Agent, Gemini CLI, dan MT5.

## Arsitektur

```
AI Risk & Operations Manager
        |
    OpenCode Agent
        |
  ┌─────┴─────┐
Gemini CLI   Ollama
(Primary)    (Fallback)
```

## Alur Decision Pipeline

```
SQLite State → Context Builder → OpenCode Agent → Decision JSON → Parser → Override Handler
```

## Struktur Proyek

```
├── config/          # Konfigurasi bot dan strategi
├── data/            # Database SQLite, log, state
├── scripts/         # Backtest, optimasi, strategi
├── src/
│   ├── audit/       # System, risk, backtest audit
│   ├── notification/# Telegram notifier
│   ├── provider/    # OpenCode CLI, Gemini CLI, Ollama
│   ├── main.py      # Entry point utama
│   ├── state_manager.py
│   ├── context_builder.py
│   ├── decision_parser.py
│   └── override_handler.py
└── tests/           # Simulasi dan test pipeline
```

## Fitur

- **System Audit** — monitoring koneksi MT5, health VPS, heartbeat
- **Risk Audit** — monitoring drawdown, Sharpe ratio, lot size
- **Backtest Audit** — validasi hasil backtest harian
- **AI Manager** — analisis via OpenCode Agent (Gemini CLI primary, Ollama fallback)
- **Telegram Alert** — notifikasi real-time untuk issue kritis
- **Override Handler** — eksekusi command operasional (reduce lot, pause strategy, alert)

## Keamanan

AI Manager **hanya** boleh:
- reduce lot
- pause strategy
- raise alert
- request revalidation / human review

AI Manager **dilarang**:
- membuka/menutup order
- menambah leverage/lot
- mengubah Statistical Gate
- menghasilkan sinyal BUY/SELL

## Instalasi

```bash
pip install -r requirements.txt
```

## Konfigurasi

Edit `config/settings.json`:
- Path database dan log
- Token dan chat ID Telegram
- Konfigurasi provider AI

## Menjalankan

```bash
python -m src.main
```

## Persyaratan

- Python 3.14+
- OpenCode CLI (default) atau Gemini CLI
- MetaTrader 5
