#!/bin/sh
# Runs as root only to give user depiqo the data volume, then runs the command as depiqo.
set -eu
mkdir -p /data/storage
if [ "$(stat -c %U /data)" != "depiqo" ] || [ "$(stat -c %U /data/storage)" != "depiqo" ]; then
  chown -R depiqo:depiqo /data
fi
exec setpriv --reuid=depiqo --regid=depiqo --init-groups "$@"
