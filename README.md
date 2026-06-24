# 🤖 Trading Bot V1.0 — AI Risk & Operations Manager

Sistem trading otomatis dengan arsitektur AI-driven untuk audit, monitoring, dan manajemen risiko. Terintegrasi dengan OpenCode Agent, Gemini CLI, dan MT5.

> "AI yang bertanggung jawab untuk memantau risiko dan operasi trading, bukan untuk melakukan trading itu sendiri."

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
│   ├── settings.json           # Konfigurasi utama
│   ├── tickers/               # Konfigurasi ticker
│   └── */                      # Konfigurasi per-ticker
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

### Audit System
- Monitoring koneksi MT5
- Monitoring kesehatan VPS
- Monitoring heartbeat

### Audit Risk
- Monitoring drawdown
- Monitoring Sharpe ratio
- Monitoring ukuran lot

### Audit Backtest
- Validasi hasil backtest harian

### AI Manager
- Analisis melalui OpenCode Agent
- Gemini CLI sebagai provider utama
- Ollama sebagai fallback

### Telegram Alert
- Notifikasi real-time untuk issue kritis

### Override Handler
- Eksekusi command operasional:
  - `reduce_lot` - mengurangi ukuran lot
  - `pause_strategy` - menghentikan strategi
  - `alert_only` - hanya mengirim alert

## Keamanan AI Manager

### Izin (Diizinkan)
- `reduce_lot` - mengurangi ukuran lot
- `pause_strategy` - menghentikan strategi
- `alert_only` - mengirim alert
- `request_revalidation` - meminta validasi ulang
- `request_human_review` - meminta tinjauan manusia

### Larangan (Dilarang)
- `buy`, `sell`, `close_position` - membuka/menutup posisi
- `increase_lot`, `increase_leverage` - meningkatkan lot/leverage
- `change_statistical_gate` - mengubah Statistical Gate
- Menghasilkan sinyal BUY/SELL

## Instalasi

```bash
pip install -r requirements.txt
```

## Konfigurasi

Edit `config/settings.json`:
- `mt5_login` - Login MT5
- `mt5_password` - Password MT5
- `mt5_server` - Server MT5

## Menjalankan

```bash
python -m src.main
```

## Persyaratan

- Python 3.14+
- OpenCode CLI (default) atau Gemini CLI
- MetaTrader 5
