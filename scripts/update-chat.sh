#!/usr/bin/env bash

set -e
set -x

# This script downloads new chat CSS/JS assets from py-shiny, and stamps the
# directory with a GIT_VERSION.

REPO_URL="https://github.com/posit-dev/py-shiny.git"
BRANCH=chat-shiny-bind
DEST_DIR="inst/lib/shiny"

if [ ! -f "shinychat.Rproj" ]; then
  echo "Error: You must execute this script from the repo root (./scripts/update-chat.sh)."
  exit 1
fi

# Clone the repository with sparse-checkout enabled
git clone -b "$BRANCH" --depth 1 "$REPO_URL" repo_tmp

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "repo_tmp/shiny/www/py-shiny/chat" "$DEST_DIR/chat"
cp -R "repo_tmp/shiny/www/py-shiny/markdown-stream" "$DEST_DIR/markdown-stream"
cp -R "repo_tmp/shiny/www/py-shiny/text-area" "$DEST_DIR/text-area"
(cd repo_tmp; git rev-parse HEAD) > "${DEST_DIR}/GIT_VERSION"
rm -rf repo_tmp
