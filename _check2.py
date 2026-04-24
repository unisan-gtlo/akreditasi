import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'akreditasi.settings')
django.setup()

from django.db import connection
cursor = connection.cursor()

def show_columns(table_name):
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'master' AND table_name = %s
        ORDER BY ordinal_position
    """, [table_name])
    rows = cursor.fetchall()
    print(f"\n=== master.{table_name} ({len(rows)} columns) ===")
    for r in rows:
        nullable = "NULL" if r[2] == "YES" else "NOT NULL"
        print(f"  {r[0]:<35} {r[1]:<25} {nullable}")

def show_sample(table_name, limit=5):
    cursor.execute(f"SELECT * FROM master.{table_name} LIMIT {limit}")
    rows = cursor.fetchall()
    cols = [c[0] for c in cursor.description]
    print(f"\n=== SAMPLE {limit} rows dari master.{table_name} ===")
    print("  " + " | ".join(cols))
    print("  " + "-" * 80)
    for r in rows:
        values = [str(v)[:30] if v is not None else "NULL" for v in r]
        print("  " + " | ".join(values))

def show_count(table_name):
    cursor.execute(f"SELECT COUNT(*) FROM master.{table_name}")
    count = cursor.fetchone()[0]
    print(f"\n=== TOTAL ROWS di master.{table_name}: {count} ===")

for tbl in ["program_studi", "prodi_pt", "fakultas"]:
    print("\n" + "=" * 70)
    print(f"TABLE: master.{tbl}")
    print("=" * 70)
    show_count(tbl)
    show_columns(tbl)
    show_sample(tbl, 5)
