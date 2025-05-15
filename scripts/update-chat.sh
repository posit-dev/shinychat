#!/usr/bin/env bash

set -e

# This script downloads new chat CSS/JS assets from py-shiny, and stamps the
# directory with a GIT_VERSION.

REPO_URL="https://github.com/posit-dev/py-shiny.git"
BRANCH="fix/chat-scroll"
DEST_DIR="inst/lib/shiny"

if [ $BRANCH != "main" ]; then
  echo "WARNING: Updating to branch '${BRANCH}'!"
  echo "WARNING: Confirm that this is correct. Do you want 'main'?"
fi

if [ ! -f "shinychat.Rproj" ]; then
  echo "ERROR: You must execute this script from the repo root (./scripts/update-chat.sh)."
  exit 1
fi

# Clone the repository with sparse-checkout enabled
echo "Cloning repository..."
git clone -b "$BRANCH" --depth 1 "$REPO_URL" repo_tmp

echo "Copying assets..."
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "repo_tmp/shiny/www/py-shiny/chat" "$DEST_DIR/chat"
cp -R "repo_tmp/shiny/www/py-shiny/markdown-stream" "$DEST_DIR/markdown-stream"
(cd repo_tmp; git rev-parse HEAD) > "${DEST_DIR}/GIT_VERSION"
echo "Cleaning up..."
rm -rf repo_tmp

echo "shinychat was updated!"
