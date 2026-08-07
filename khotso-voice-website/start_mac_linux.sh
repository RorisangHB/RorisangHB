#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  printf '\nA new .env file was created. Add OPENAI_API_KEY and APP_PASSWORD, then run this script again.\n'
  exit 1
fi

python3 app.py
