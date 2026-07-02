#!/bin/bash
# Wrapper: refresh WTTJ JWT token then start the MCP server via Docker.
# Called by Claude Code MCP config in ~/.claude.json
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

# Refresh token if needed (opens Chrome briefly, then closes it)
python3 "$SCRIPT_DIR/refresh_token.py" >&2

# Hand off to Docker MCP server (exec keeps stdin/stdout clean for MCP protocol)
exec docker run --rm -i \
    --platform linux/arm64 \
    --env-file "$ENV_FILE" \
    wttj-mcp:latest
