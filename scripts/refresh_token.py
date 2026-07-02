#!/usr/bin/env python3
"""
Retrieves a fresh WTTJ session cookie and saves it to .env.
Strategy:
  1. Use Playwright to load the signin page (runs JavaScript → sets csrf-token cookie)
  2. Extract cookies (wttj_api_session_key + csrf-token) from the browser
  3. Use httpx to POST credentials to /api/v1/sessions with the CSRF header
  4. Extract the authenticated session cookie from the response
  5. Save WTTJ_SESSION_KEY to .env

This is faster than letting the browser submit the form (step 3 is a direct HTTP call).
Runs automatically before the MCP server starts (via start_mcp.sh).
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SIGNIN_URL = "https://www.welcometothejungle.com/fr/signin"
SESSION_COOKIE_NAME = "wttj_api_session_key"
CSRF_COOKIE_NAME = "csrf-token"

# Refresh if session is older than 50 minutes (sessions appear to last ~2h)
SESSION_MAX_AGE_SECONDS = 3000


def _read_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env(env: dict) -> None:
    lines = []
    written: set = set()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in env:
                    lines.append(f"{k}={env[k]}")
                    written.add(k)
                    continue
            lines.append(line)
    for k, v in env.items():
        if k not in written:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def _ts_file() -> Path:
    return ENV_FILE.parent / ".wttj_session_ts"


def _session_still_fresh(env: dict) -> bool:
    if not env.get("WTTJ_SESSION_KEY"):
        return False
    ts_file = _ts_file()
    if not ts_file.exists():
        return False
    try:
        ts = float(ts_file.read_text().strip())
        return time.time() - ts < SESSION_MAX_AGE_SECONDS
    except Exception:
        return False


def _save_ts() -> None:
    _ts_file().write_text(str(time.time()))


async def _get_initial_cookies() -> dict:
    """Open the WTTJ signin page in a real browser to get the CSRF session cookies."""
    from playwright.async_api import async_playwright

    cookies = {}
    async with async_playwright() as p:
        use_chrome = os.path.exists(CHROME_PATH)
        browser = await p.chromium.launch(
            executable_path=CHROME_PATH if use_chrome else None,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
        )
        page = await context.new_page()

        print("[refresh_token] Loading WTTJ signin page to get CSRF cookies...", flush=True)
        await page.goto(SIGNIN_URL, wait_until="domcontentloaded", timeout=30000)

        # Wait for JavaScript to set the csrf-token cookie
        for _ in range(10):
            all_cookies = {c["name"]: c["value"] for c in await context.cookies()}
            if CSRF_COOKIE_NAME in all_cookies:
                break
            await asyncio.sleep(0.5)

        cookies = {c["name"]: c["value"] for c in await context.cookies()}
        await browser.close()

    return cookies


async def _do_login(email: str, password: str, browser_cookies: dict) -> str:
    """POST credentials to WTTJ API and return the authenticated session key."""
    csrf_token = browser_cookies.get(CSRF_COOKIE_NAME, "")
    if not csrf_token:
        raise RuntimeError(f"Could not get {CSRF_COOKIE_NAME} from browser session")

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.post(
            "https://api.welcometothejungle.com/api/v1/sessions",
            files={
                "session[email]": (None, email),
                "session[password]": (None, password),
                "session[remember_me]": (None, "false"),
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Origin": "https://www.welcometothejungle.com",
                "Referer": "https://www.welcometothejungle.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
                ),
                "wttj-user-language": "fr",
                "x-csrf-token": csrf_token,
                "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            cookies=browser_cookies,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Login failed ({resp.status_code}): {resp.text[:300]}"
        )

    # The new authenticated session cookie is in the response cookies
    session_key = resp.cookies.get(SESSION_COOKIE_NAME)

    # Fallback: parse Set-Cookie header directly
    if not session_key:
        set_cookie = resp.headers.get("set-cookie", "")
        for part in set_cookie.split(";"):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                session_key = part[len(SESSION_COOKIE_NAME) + 1:]
                break

    if not session_key:
        raise RuntimeError(
            "Login succeeded but could not find wttj_api_session_key in response. "
            f"Response cookies: {dict(resp.cookies)}"
        )

    return session_key


def main():
    env = _read_env()

    if _session_still_fresh(env):
        print("[refresh_token] Session still fresh, skipping refresh.", flush=True)
        return

    email = env.get("WTTJ_EMAIL")
    password = env.get("WTTJ_PASSWORD")
    if not email or not password:
        print(
            "[refresh_token] ERROR: WTTJ_EMAIL and WTTJ_PASSWORD must be set in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[refresh_token] Refreshing session for {email}...", flush=True)

    browser_cookies = asyncio.run(_get_initial_cookies())
    print(
        f"[refresh_token] Got {len(browser_cookies)} cookies from browser "
        f"(csrf={CSRF_COOKIE_NAME in browser_cookies})",
        flush=True,
    )

    session_key = asyncio.run(_do_login(email, password, browser_cookies))
    print(f"[refresh_token] Authenticated session key: {session_key[:30]}...", flush=True)

    env["WTTJ_SESSION_KEY"] = session_key
    _write_env(env)
    _save_ts()
    print("[refresh_token] .env updated with fresh WTTJ_SESSION_KEY.", flush=True)


if __name__ == "__main__":
    main()
