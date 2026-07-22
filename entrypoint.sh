#!/bin/sh
set -e

# PUID/PGID: optioneel, standaard 1000/1000 (dezelfde UID/GID als
# appuser, gezet in de Dockerfile). Dit volgt de conventie van
# LinuxServer.io-achtige images -- handig op een NAS (OMV, Synology,
# Unraid) waar het gemounte data-volume vaak met een andere
# eigenaar/permissies wordt aangemaakt dan de vaste UID in de image.
#
# Zonder deze aanpassing faalt SQLite met "unable to open database
# file" zodra /app/data niet beschrijfbaar is voor de vaste appuser
# (UID 1000) uit de Dockerfile.

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

CURRENT_UID="$(id -u appuser)"
CURRENT_GID="$(id -g appuser)"

if [ "$PUID" != "$CURRENT_UID" ] || [ "$PGID" != "$CURRENT_GID" ]; then
    echo "entrypoint: appuser aanpassen naar PUID=$PUID PGID=$PGID"
    groupmod -o -g "$PGID" appuser
    usermod -o -u "$PUID" appuser
fi

# Zorg dat het gemounte data-volume beschrijfbaar is voor appuser,
# ongeacht welke eigenaar de map op de host (NAS) had. -R is hier
# bewust beperkt tot /app/data (niet heel /app) -- dat blijft van de
# image zelf, alleen de gemounte, persistente map hoeft aangepast.
mkdir -p /app/data/backups
chown -R "$PUID":"$PGID" /app/data

echo "entrypoint: starten als PUID=$PUID PGID=$PGID"

exec gosu appuser "$@"
