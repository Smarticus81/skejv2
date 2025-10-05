import sqlite3

conn = sqlite3.connect('data/psur_schedule.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='psur_reports'")
row = cur.fetchone()
if row:
    print("Current schema:")
    print(row[0])
    print("\n" + "="*60)
    if "td_number TEXT UNIQUE" in row[0]:
        print("⚠️  UNIQUE constraint found on td_number - this needs migration!")
    else:
        print("✅ No UNIQUE constraint on td_number - duplicates allowed")
else:
    print("No psur_reports table found")
conn.close()
