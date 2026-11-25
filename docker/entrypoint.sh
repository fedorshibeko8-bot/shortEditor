#!/bin/sh
set -eu

mkdir -p /app/data/downloads /app/data/audio /app/data/rendered /app/logs
exec "$@"
