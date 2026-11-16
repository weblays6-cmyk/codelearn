
import os
import sys
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myblog.settings")
django.setup()

from django.db import connection

TABLES = [
    "blog_xpevent",
    "blog_notification",
    "blog_userprofile",
    "blog_streakfreeze",
    "blog_dailytopperformer",
]

with connection.cursor() as cursor:
    for table in TABLES:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=%s",
            [table],
        )
        exists = cursor.fetchone()

        print(f"\n{'=' * 50}")
        print(f"TABLE: {table} | EXISTS: {bool(exists)}")

        if exists:
            cursor.execute(f'PRAGMA table_info("{table}")')
            for column in cursor.fetchall():
                print(column)

    cursor.execute('PRAGMA table_info("blog_xpevent")')
    xp_columns = {column[1] for column in cursor.fetchall()}
    if "source_key" in xp_columns:
        xp_fields = (
            "id, user_id, event_type, points, source_key, verified, created_at"
        )
    else:
        xp_fields = (
            "id, user_id, event_type, points, source_type, source_id, "
            "is_verified, created_at"
        )
    cursor.execute(f"SELECT {xp_fields} FROM blog_xpevent ORDER BY id")
    print("\nEXISTING XP RECORDS:")
    for record in cursor.fetchall():
        print(record)

    cursor.execute(
        "SELECT COUNT(*), "
        "SUM(CASE WHEN conversation_id IS NOT NULL THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN assignment_id IS NOT NULL THEN 1 ELSE 0 END) "
        "FROM blog_notification"
    )
    print("\nNOTIFICATION COUNTS (total, conversation_id, assignment_id):")
    print(cursor.fetchone())

print("\nInspection complete. No database changes made.")
