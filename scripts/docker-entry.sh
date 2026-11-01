#!/bin/sh
# Fly mounts volumes as root, so take ownership and then drop privileges.
set -e
chown -R app:app /data
exec setpriv --reuid=app --regid=app --init-groups "$@"
