# AI Collaboration Handoff System

Kamu adalah salah satu dari 2 AI (Dev atau Reviewer) yang bekerja sama mengembangkan project trading bot ini.

## Cara kerja

### 1. BACA file `data/agent_handoff.json`
File ini adalah jembatan komunikasi. Isinya:

```json
{
  "task": { "id": 1, "title": "...", "description": "...", "assigned_to": "dev", "priority": "..." },
  "status": "pending|in_progress|review_needed|feedback_given|done",
  "result": "kode yang ditulis dev",
  "feedback": "review dari reviewer",
  "notes": [],
  "round": 0
}
```

### 2. Tentukan peranmu
- **assigned_to = "dev"** → lo yang ngerjain task
- **assigned_to = "reviewer"** → lo yang nge-review hasil dev
- **status = "review_needed"** → giliran reviewer
- **status = "feedback_given"** → giliran dev (revisi)
- **status = "done"** → task selesai

### 3. Alur kolaborasi

```
Dev kerjakan task         → status = "review_needed", tulis hasil di "result"
Reviewer baca hasil        → kasih feedback di "feedback"
  ├ Kalau OK               → status = "done"
  └ Kalau perlu revisi     → status = "feedback_given", assigned_to = "dev"
Dev baca feedback          → perbaiki, update "result", status = "review_needed"
Reviewer review lagi       → loop sampe OK
```

### 4. Format kode di "result"
Tulis file path + isi kode yang lo buat/ubah.
Reviewer bisa langsung ngecek file real-nya.

## Rules
- JANGAN edit `data/agent_handoff.json` secara manual di tengah proses — biarin AI yg handle
- Kalo bingung, tanya dulu di "notes"
- Satu task selesai → ajukan task baru
