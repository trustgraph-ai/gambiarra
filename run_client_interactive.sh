#!/bin/bash
# Run Gambiarra client interactively in WORKSPACE directory

cd WORKSPACE
export GAMBIARRA_SERVER_URL="ws://127.0.0.1:8010/ws"
export GAMBIARRA_WORKSPACE="$(pwd)"
export GAMBIARRA_AUTO_APPROVE_READS="true"

echo "🚀 Starting Gambiarra Client"
echo "📂 Workspace: $(pwd)"
echo "🔗 Server: $GAMBIARRA_SERVER_URL"
echo ""
echo "Type your message when prompted..."
echo ""

python -m gambiarra.client.main
