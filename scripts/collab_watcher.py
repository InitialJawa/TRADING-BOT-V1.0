"""Watcher untuk auto-trigger kolaborasi 2 AI via file handoff.

Cara pakai:
  python scripts/collab_watcher.py

Bisa juga di tab terpisah biar jalan terus.
"""

import json
import os
import shutil
import subprocess
import sys
import time

HANDOFF = "data/agent_handoff.json"
POLL_INTERVAL = 10  # detik

DEV_AGENT = "collab-dev"
REVIEWER_AGENT = "collab-reviewer"

OPCODE_CMD = os.environ.get("OPCODE_CMD") or shutil.which("opencode") or shutil.which("opencode.cmd")
if not OPCODE_CMD:
    raise RuntimeError("opencode not found in PATH. Install it or set OPCODE_CMD env var.")


def load_handoff():
    if not os.path.exists(HANDOFF):
        return None
    with open(HANDOFF) as f:
        return json.load(f)


def get_status(data):
    return data.get("status", "")


def run_agent(agent_name):
    prompt = f"Check {HANDOFF} dan lakukan tugasmu sesuai peran."
    print(f"\n{'='*50}")
    print(f"[WATCHER] Triggering {agent_name}...")
    print(f"{'='*50}")
    try:
        cmd = f'"{OPCODE_CMD}" run "{prompt}" --agent {agent_name} --pure'
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", shell=True
        )
        out = result.stdout.strip() or result.stderr.strip()
        print(f"[WATCHER] {agent_name} done.")
        if out:
            print(f"[WATCHER] Output: {out[:500]}")
        return True
    except subprocess.TimeoutExpired:
        print(f"[WATCHER] {agent_name} timed out after 120s")
        return False
    except Exception as e:
        print(f"[WATCHER] {agent_name} error: {e}")
        return False


def main():
    print("[WATCHER] Collaboration watcher started.")
    print(f"[WATCHER] Polling {HANDOFF} every {POLL_INTERVAL}s")
    print(f"[WATCHER] Dev={DEV_AGENT}, Reviewer={REVIEWER_AGENT}")
    print("[WATCHER] Press Ctrl+C to stop.\n")

    last_status = ""

    while True:
        try:
            data = load_handoff()
            if data is None:
                time.sleep(POLL_INTERVAL)
                continue

            s = get_status(data)
            assigned = data.get("task", {}).get("assigned_to", "")

            if s == "done":
                if last_status != "done":
                    print(f"\n[WATCHER] Task #{data['task']['id']} SELESAI!")
                    print("[WATCHER] Menunggu task baru...\n")
                last_status = "done"
                time.sleep(POLL_INTERVAL)
                continue

            if s == "pending" and assigned == "dev":
                run_agent(DEV_AGENT)
            elif s == "feedback_given" and assigned == "dev":
                run_agent(DEV_AGENT)
            elif s == "review_needed" and assigned == "reviewer":
                run_agent(REVIEWER_AGENT)
            elif s == "in_progress":
                pass
            else:
                pass

            last_status = s
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\n[WATCHER] Stopped by user.")
            sys.exit(0)
        except Exception as e:
            print(f"[WATCHER] Error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
