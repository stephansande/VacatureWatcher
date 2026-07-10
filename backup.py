import os

import shutil

from datetime import datetime

from config import Config



BACKUP_FOLDER = "data/backups"



def create_backup():


    os.makedirs(
        BACKUP_FOLDER,
        exist_ok=True
    )


    source = Config.DATABASE_PATH


    filename = (
        "vacaturewatcher_"
        +
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
        +
        ".db"
    )


    destination = os.path.join(
        BACKUP_FOLDER,
        filename
    )


    shutil.copy2(
        source,
        destination
    )


    return destination