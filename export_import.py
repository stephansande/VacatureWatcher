import shutil

import os



EXPORT_FOLDER = "data/export"



def export_database(
    database_path
):

    os.makedirs(
        EXPORT_FOLDER,
        exist_ok=True
    )


    target = os.path.join(
        EXPORT_FOLDER,
        "vacaturewatcher_export.db"
    )


    shutil.copy2(
        database_path,
        target
    )


    return target




def import_database(
    source,
    destination
):

    shutil.copy2(
        source,
        destination
    )


    return True