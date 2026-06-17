import subprocess, os, tempfile
OPCODE = r"C:\Users\BedilGaib\AppData\Roaming\npm\opencode.cmd"
prompt = 'Balas HANYA JSON: {"status":"ok"}'
env = os.environ.copy()
env["GOOGLE_GENERATIVE_AI_API_KEY"] = env.get("GEMINI_API_KEY", "")
tmp = tempfile.mkdtemp()
r = subprocess.run([OPCODE, "run", prompt, "-m", "google/gemini-2.5-flash", "--pure"], capture_output=True, text=True, timeout=30, cwd=tmp, env=env)
print("STDOUT:", repr(r.stdout[:300]))
print("STDERR:", repr(r.stderr[:300]))
