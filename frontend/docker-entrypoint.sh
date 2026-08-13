#!/bin/sh
# Runs automatically at container startup (nginx's image executes every /docker-entrypoint.d/*.sh
# before starting nginx). Writes window.__API_URL__ from the API_URL env var Cloud Run passes in,
# so the same built image works against whichever backend URL this revision is configured with -
# no rebuild needed to point the frontend at a different backend.
set -e
echo "window.__API_URL__ = \"${API_URL:-}\";" > /usr/share/nginx/html/env.js
