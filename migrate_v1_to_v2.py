"""
Eenmalig migratiescript: v1-database -> v2-schema.

app.py gebruikt db.create_all(), en dat voegt GEEN kolommen toe aan
een tabel die al bestaat, en hernoemt al helemaal geen tabellen. Als
je al een draaiende v1-installatie hebt (met vacatures/werkgevers
erin), draai dan dit script EENMALIG voordat je de v2-code voor het
eerst start:

    python migrate_v1_to_v2.py

Nieuwe installaties hebben dit niet nodig: db.create_all() maakt de
"source"-tabel daar meteen met alle kolommen aan.

Dit script is idempotent: opnieuw draaien op een reeds gemigreerde
database doet niets (het herkent dat de "source"-tabel al bestaat).

Voor structurele toekomstige wijzigingen raad ik aan om over te
stappen op Flask-Migrate/Alembic in plaats van handmatige ALTER
TABLE-scripts zoals dit.
"""

import sqlite3

from config import Config


NEW_COLUMNS = [
    ("type", "VARCHAR(20) DEFAULT 'employer' NOT NULL"),
    ("adapter", "VARCHAR(50) DEFAULT 'generic_links' NOT NULL"),
    ("settings", "TEXT"),
]


def migrate():

    database_path = Config.DATABASE_PATH

    print(f"Migreren van database: {database_path}")

    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()

    table_names = {
        row[0]
        for row in cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if "source" in table_names:
        print("  - tabel 'source' bestaat al, migratie eerder uitgevoerd, klaar")
        connection.close()
        return

    if "employer" not in table_names:
        print("  - geen 'employer'-tabel gevonden (nieuwe installatie?), niets te doen")
        connection.close()
        return

    print("  - hernoemen van tabel 'employer' naar 'source'")
    cursor.execute("ALTER TABLE employer RENAME TO source")

    cursor.execute("PRAGMA table_info(source)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for column_name, column_definition in NEW_COLUMNS:

        if column_name in existing_columns:
            print(f"  - kolom '{column_name}' bestaat al, overslaan")
            continue

        statement = f"ALTER TABLE source ADD COLUMN {column_name} {column_definition}"

        print(f"  - toevoegen: {column_name}")

        cursor.execute(statement)

    connection.commit()
    connection.close()

    print("Migratie voltooid.")


if __name__ == "__main__":
    migrate()
