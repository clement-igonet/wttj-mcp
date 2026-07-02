# wttj-mcp

MCP server for [Welcome to the Jungle](https://www.welcometothejungle.com) — search jobs and companies, read your profile, all from Claude.

## Tools

### Authentication
| Tool | Description |
|------|-------------|
| `login` | Authenticate with email/password. Optional if `WTTJ_EMAIL` / `WTTJ_PASSWORD` env vars are set — auto-login happens on first tool call. |

### Your profile
| Tool | Description |
|------|-------------|
| `get_my_profile` | Full profile: location, job search status, resume metadata |
| `get_my_work_experiences` | Work history |
| `get_my_skills` | Skills list |
| `get_my_educations` | Education history |

### Job search
| Tool | Description |
|------|-------------|
| `search_jobs` | Full-text + faceted search via Algolia. Filters: `contract_type`, `remote`, `experience_level_min/max`, `salary_min`, `profession_category`, `organization_slug`, `around_lat_lng` + radius |
| `get_job` | Full job posting detail (description, missions, profile, salary, benefits, apply URL…) |
| `get_job_filters` | All available filter values (professions, contract types, etc.) |

### Company search
| Tool | Description |
|------|-------------|
| `search_companies` | Search companies by name, sector, or location via Algolia |
| `get_company` | Company detail: description, offices, sectors, size |
| `get_company_jobs` | All open jobs for a given company |

### Utilities
| Tool | Description |
|------|-------------|
| `autocomplete_location` | Turn a partial location string into lat/lng coordinates (pass the result to `search_jobs`) |

## Setup

### 1. Install dependencies

```bash
pip install playwright httpx
python -m playwright install chromium
```

### 2. Build the Docker image

```bash
git clone https://github.com/clement-igonet/wttj-mcp.git
cd wttj-mcp
docker build --platform linux/arm64 -t wttj-mcp:latest .
```

> **amd64 / Linux?** Drop `--platform linux/arm64`.

### 3. Configure credentials

```bash
cp .env.example .env
# Edit .env: fill in WTTJ_EMAIL and WTTJ_PASSWORD
```

### 4. Add to Claude Code

Add to `~/.claude.json` under `mcpServers`:

```json
"wttj": {
  "command": "/bin/bash",
  "args": ["/absolute/path/to/wttj-mcp/scripts/start_mcp.sh"]
}
```

Restart Claude Code — authentication is fully automatic.

### How authentication works

On each startup, `scripts/start_mcp.sh` runs `scripts/refresh_token.py` which:
1. Opens Chrome briefly to get a CSRF token from the WTTJ signin page
2. Posts your credentials directly via the WTTJ API (no form, no reCAPTCHA)
3. Saves the session cookie to `.env` as `WTTJ_SESSION_KEY`
4. Starts the Docker MCP server

The session is cached for ~50 minutes and reused across restarts.

## Example prompts

```
Find remote DevOps jobs in France with a salary above 60k€
```
```
Show me all open positions at Criteo
```
```
What companies near Toulouse are hiring in the Tech sector?
```
```
Compare this job offer with my current profile and tell me if I'm a good match
```
