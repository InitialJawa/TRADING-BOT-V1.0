# PRD v1.1 — AI Manager Refactor (OpenCode Architecture)

## Perubahan Besar

### Sebelum

Layer 0 dirancang sebagai:

- Observer
- Market analyzer
- Override engine

Menggunakan:

- Claude API
- GPT-4o API

Polling setiap beberapa jam.

### Sesudah

Layer 0 diubah menjadi:

## AI Risk & Operations Manager

Tujuan:

- Monitoring kesehatan sistem
- Monitoring performa strategi
- Monitoring drawdown
- Monitoring hasil backtest
- Monitoring anomali data
- Monitoring koneksi MT5

AI tidak menentukan entry dan exit trading.

AI tidak menghasilkan sinyal BUY atau SELL.

Semua keputusan trading tetap berasal dari:

- Strategy Engine
- Risk Manager
- Statistical Gate

AI hanya memiliki wewenang operasional terbatas.

---

# Layer 0 — AI Risk & Operations Manager

## Arsitektur Baru

```text
┌─────────────────────────────────────┐
│      AI Risk & Operations Manager   │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│           OpenCode Agent            │
└────────────────┬────────────────────┘
                 │
         ┌───────┴─────────┐
         │                 │
         ▼                 ▼
    Gemini CLI         Ollama
    (Primary)          (Fallback)
```

## Responsibilities

AI Manager bertanggung jawab untuk:

- Audit performa strategy
- Audit drawdown
- Audit hasil backtest
- Audit system health
- Audit data quality
- Audit VPS health
- Audit MT5 connectivity

AI Manager tidak bertanggung jawab untuk:

- Membuka posisi
- Menutup posisi
- Menentukan arah market
- Mengganti strategy aktif
- Mengubah risk limit

---

## Input Context

AI menerima:

```json
{
  "portfolio_drawdown": 8.4,
  "rolling_sharpe_7d": 0.55,
  "strategy_status": {
    "adaptive": "ACTIVE",
    "trend_re": "ACTIVE"
  },
  "mt5_connection": true,
  "heartbeat_status": "OK",
  "recent_errors": [],
  "backtest_status": "PASS"
}
```

## Output Command

### Command yang diizinkan

```json
{
  "action": "alert_only"
}
```

```json
{
  "action": "reduce_lot",
  "target": "xauusdm",
  "value": 0.5
}
```

```json
{
  "action": "pause_strategy",
  "target": "trend_re"
}
```

### Command yang dilarang

```json
{
  "action": "BUY"
}
```

```json
{
  "action": "SELL"
}
```

```json
{
  "action": "CLOSE_POSITION"
}
```

---

# OpenCode Integration

## Primary Provider

Gemini CLI

```bash
gemini
```

Digunakan sebagai provider utama karena:

- Gratis
- Context besar
- Cocok untuk audit sistem

## Fallback Provider

Ollama Local

Model yang direkomendasikan:

- Qwen3 14B
- Qwen3 32B
- DeepSeek R1 Distill

Digunakan saat:

- Gemini tidak tersedia
- Rate limit
- Koneksi internet bermasalah

---

# AI Decision Pipeline

```text
SQLite State
      |
      v
Context Builder
      |
      v
OpenCode Agent
      |
      v
Decision JSON
      |
      v
Parser
      |
      v
Override Handler
```

Semua output harus valid JSON.

Jika parsing gagal:

- abaikan keputusan
- kirim alert Telegram
- log ke ai_errors.log

---

# Cost Reduction

## Sebelum

Claude API + GPT API

Estimasi: $5–20 / bulan

## Sesudah

Gemini CLI

Estimasi: $0 atau mendekati nol.

---

# Safety Rules

AI Manager tidak boleh:

- membuka order
- menutup order
- menambah leverage
- menaikkan lot size
- menonaktifkan drawdown guard
- mengubah Statistical Gate

AI Manager hanya boleh:

- reduce lot
- pause strategy
- raise alert
- request revalidation
- request human review

---

# Phase Update

Phase 4 diubah menjadi:

## Phase 4 — AI Risk & Operations Manager

Deliverables:

- OpenCode integration
- Gemini CLI connector
- Ollama fallback
- Structured JSON output
- System audit engine
- Risk audit engine
- Backtest audit engine
- Telegram escalation

Definition of Done:

AI berhasil mendeteksi:

- drawdown breach
- MT5 disconnect
- backtest failure
- heartbeat failure

dan menghasilkan tindakan operasional yang benar tanpa campur tangan pada keputusan trading.
