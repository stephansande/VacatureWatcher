"""
Migratiescript: brengt een bestaande database bij naar het huidige
v2-schema. app.py gebruikt db.create_all(), en dat voegt GEEN
kolommen toe aan een tabel die al bestaat, en hernoemt al helemaal
geen tabellen. Draai dit script daarom EENMALIG bij elke upgrade:

    python migrate_v1_to_v2.py

Dit script is idempotent en cumulatief: het kan veilig meerdere keren
gedraaid worden (bv. na elke Fase), en pakt bij elke run alleen de
kolommen op die nog ontbreken -- ook als de "source"-tabel al bestaat
van een eerdere migratie. Nieuwe installaties hebben dit niet nodig:
db.create_all() maakt de "source"-tabel daar meteen met alle kolommen
in één keer aan.

Voor structurele toekomstige wijzigingen raad ik aan om over te
stappen op Flask-Migrate/Alembic in plaats van handmatige ALTER
TABLE-scripts zoals dit.
"""

import sqlite3

from config import Config


# (kolomnaam, SQL-typedefinitie) -- cumulatief over alle fases heen.
# Kolommen die in een eerdere fase al zijn toegevoegd, worden bij een
# volgende run automatisch overgeslagen (zie migrate() hieronder).
NEW_COLUMNS = [
    # Fase 1
    ("type", "VARCHAR(20) DEFAULT 'employer' NOT NULL"),
    ("adapter", "VARCHAR(50) DEFAULT 'generic_links' NOT NULL"),
    ("settings", "TEXT"),
    # Fase 2 -- bronstatus
    ("last_success", "DATETIME"),
    ("last_error", "TEXT"),
    ("last_new_count", "INTEGER"),
    # Fase 3 -- weekdag-selectie voor het controleschema
    ("check_days", "VARCHAR(30) DEFAULT 'mon,tue,wed,thu,fri,sat,sun' NOT NULL"),
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

    if "source" not in table_names:

        if "employer" not in table_names:
            print("  - geen 'employer'- of 'source'-tabel gevonden "
                  "(nieuwe installatie?), niets te doen")
            connection.close()
            return

        print("  - hernoemen van tabel 'employer' naar 'source'")
        cursor.execute("ALTER TABLE employer RENAME TO source")

    else:
        print("  - tabel 'source' bestaat al, ga verder met kolommen controleren")

    cursor.execute("PRAGMA table_info(source)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    added_any = False

    for column_name, column_definition in NEW_COLUMNS:

        if column_name in existing_columns:
            print(f"  - kolom '{column_name}' bestaat al, overslaan")
            continue

        statement = f"ALTER TABLE source ADD COLUMN {column_name} {column_definition}"

        print(f"  - toevoegen: {column_name}")

        cursor.execute(statement)
        added_any = True

    connection.commit()
    connection.close()

    if added_any:
        print("Migratie voltooid (kolommen toegevoegd).")
    else:
        print("Migratie voltooid (niets te doen, alles was al up-to-date).")


if __name__ == "__main__":
    migrate()
