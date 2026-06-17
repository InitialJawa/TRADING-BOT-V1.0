import sqlite3, os

for db_name in os.listdir("data"):
    if not db_name.endswith(".db"): continue
    path = f"data/{db_name}"
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"\n{db_name}: {tables}")
    for t in tables:
        cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
        print(f"  {t}: {cursor.fetchone()[0]} rows")
    conn.close()
