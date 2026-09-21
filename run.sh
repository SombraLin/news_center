#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

echo "启动 news_center 服务 (使用: $PYTHON_EXEC)..."
exec "$PYTHON_EXEC" -m app.main
