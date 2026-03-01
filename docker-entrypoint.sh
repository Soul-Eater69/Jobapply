#!/bin/sh
set -e

# Create persistent data directories (safe if already exist)
mkdir -p /app/data /app/sessions /app/resumes /app/cover_letters

# If user_profile.yaml was mounted as an empty directory by mistake
# (happens when the host file doesn't exist), replace with the default.
if [ -d /app/user_profile.yaml ]; then
    rm -rf /app/user_profile.yaml
    cp /app/user_profile.default.yaml /app/user_profile.yaml
fi

# If not mounted at all, copy the default into place
if [ ! -f /app/user_profile.yaml ]; then
    cp /app/user_profile.default.yaml /app/user_profile.yaml
fi

exec "$@"
