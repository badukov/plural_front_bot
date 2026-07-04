import json
import sqlite3
from pathlib import Path


db_path = Path("data/bot.sqlite3")
if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}")

con = sqlite3.connect(db_path)
cur = con.cursor()

expected_counts = {
    "members": 632,
    "groups": 179,
    "member_groups": 4752,
    "custom_fields": 5,
}

print("Database counts:")
for table in ["members", "groups", "member_groups", "custom_fields", "front_state", "users", "events"]:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    expected = expected_counts.get(table)
    suffix = f" (expected {expected})" if expected is not None else ""
    status = " OK" if expected is None or count == expected else " CHECK"
    print(f"{table}: {count}{suffix}{status}")

cur.execute("""
SELECT COUNT(*)
FROM members
WHERE COALESCE(TRIM(name), '') = ''
""")
print(f"\nMembers without name: {cur.fetchone()[0]}")

cur.execute("""
SELECT COUNT(*)
FROM (
    SELECT name
    FROM members
    GROUP BY name COLLATE NOCASE
    HAVING COUNT(*) > 1
)
""")
print(f"Duplicate name groups: {cur.fetchone()[0]}")

cur.execute("""
SELECT COUNT(*)
FROM members m
LEFT JOIN member_groups mg ON mg.member_id = m.id
WHERE mg.group_id IS NULL
""")
print(f"Members without categories: {cur.fetchone()[0]}")

cur.execute("""
SELECT COUNT(*)
FROM member_groups mg
LEFT JOIN members m ON m.id = mg.member_id
WHERE m.id IS NULL
""")
print(f"Broken member links: {cur.fetchone()[0]}")

cur.execute("""
SELECT COUNT(*)
FROM member_groups mg
LEFT JOIN groups g ON g.id = mg.group_id
WHERE g.id IS NULL
""")
print(f"Broken group links: {cur.fetchone()[0]}")

con.close()

report = Path("data/import_report.json")
if report.exists():
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("\nImport report: present, but not valid JSON")
    else:
        print("\nImport report summary:")
        for key in [
            "members_imported",
            "groups_imported",
            "member_group_links_imported",
            "custom_fields_imported",
            "warnings_count",
        ]:
            if key in data:
                print(f"{key}: {data[key]}")
