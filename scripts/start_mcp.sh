#!/bin/bash
# Wrapper: refresh WTTJ session key then start the MCP server directly on the host.
# Running via uv (not Docker) avoids Socktainer bridge-network DNS issues.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# Refresh session key if needed (opens Chrome briefly, then closes it)
python3 "$SCRIPT_DIR/refresh_token.py" >&2

# Load .env so WTTJ_SESSION_KEY and credentials are available
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Run MCP server directly via uv (handles venv + deps automatically)
cd "$PROJECT_DIR"
exec uv run wttj-mcp
