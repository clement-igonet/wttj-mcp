import asyncio
import json
import os
from typing import Optional
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Welcome to the Jungle")

WTTJ_API = "https://api.welcometothejungle.com"
ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_DSN = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net"
ALGOLIA_PUBLIC_KEY = "4bd8f6215d0cc52b26430765769e65a0"
JOB_INDEX = "wttj_jobs_production_fr"
COMPANY_INDEX = "wk_cms_organizations_production"


class _Session:
    def __init__(self) -> None:
        self.jwt_token: Optional[str] = None
        self.algolia_api_key: Optional[str] = None
        self.user_reference: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def api_headers(self) -> dict:
        headers = {
            "Accept": "application/json",
            "wttj-user-language": "fr",
            "User-Agent": "Mozilla/5.0 (compatible; WTTJmcp/1.0)",
        }
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        return headers

    def algolia_headers(self) -> dict:
        return {
            "x-algolia-application-id": ALGOLIA_APP_ID,
            "x-algolia-api-key": self.algolia_api_key or ALGOLIA_PUBLIC_KEY,
            "Content-Type": "application/json",
        }

    def _raise_if_unauthenticated(self) -> None:
        if not self.jwt_token:
            raise RuntimeError(
                "Not authenticated. Call the 'login' tool first, or set "
                "WTTJ_EMAIL and WTTJ_PASSWORD environment variables."
            )


_session = _Session()


async def _auto_login() -> None:
    email = os.getenv("WTTJ_EMAIL")
    password = os.getenv("WTTJ_PASSWORD")
    if email and password and not _session.jwt_token:
        await _do_login(email, password)


async def _do_login(email: str, password: str) -> dict:
    data = {"session[email]": email, "session[password]": password}
    resp = await _session.client.post(
        f"{WTTJ_API}/api/v1/sessions",
        data=data,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; WTTJmcp/1.0)",
        },
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Login failed ({resp.status_code}): {resp.text[:200]}")

    body = resp.json()
    user = body.get("user", {})
    _session.jwt_token = user.get("token")
    _session.algolia_api_key = user.get("algolia_api_key") or ALGOLIA_PUBLIC_KEY
    _session.user_reference = user.get("reference")
    return user


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@mcp.tool()
async def login(email: str, password: str) -> str:
    """Authenticate with Welcome to the Jungle using email and password.

    Must be called before any tool that requires authentication.
    Alternatively set WTTJ_EMAIL and WTTJ_PASSWORD env vars for auto-login.
    """
    user = await _do_login(email, password)
    name = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
    return json.dumps({
        "status": "authenticated",
        "name": name,
        "email": user.get("email"),
        "reference": user.get("reference"),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_my_profile() -> str:
    """Get the authenticated user's full profile (location, job search status, resume…)."""
    await _auto_login()
    _session._raise_if_unauthenticated()
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v2/users/me",
        headers=_session.api_headers(),
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_my_work_experiences() -> str:
    """Get the authenticated user's work experience history."""
    await _auto_login()
    _session._raise_if_unauthenticated()
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/users/me/work_experiences",
        headers=_session.api_headers(),
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_my_skills() -> str:
    """Get the authenticated user's skills list."""
    await _auto_login()
    _session._raise_if_unauthenticated()
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/users/me/skills",
        headers=_session.api_headers(),
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def get_my_educations() -> str:
    """Get the authenticated user's education history."""
    await _auto_login()
    _session._raise_if_unauthenticated()
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/users/me/educations",
        headers=_session.api_headers(),
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Location autocomplete
# ---------------------------------------------------------------------------

@mcp.tool()
async def autocomplete_location(query: str, lang: str = "fr", limit: int = 10) -> str:
    """Autocomplete a location name (city, region, country).

    Returns a list of matching locations with lat/lng coordinates useful for
    passing to search_jobs as location filters.

    Args:
        query: Partial location string (e.g. "Toulouse", "Paris", "France")
        lang:  Language code for result labels ("fr" or "en")
        limit: Maximum number of suggestions (1-20)
    """
    params = {"q": query, "lang": lang, "limit": min(max(1, limit), 20)}
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/geolocation/autocomplete",
        params=params,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Job filters
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_job_filters() -> str:
    """Return all available job filter options (professions, contract types, etc.)."""
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/search/job_filters",
        params={"useNewProfessions": "true"},
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Job search (Algolia)
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_jobs(
    query: str = "",
    page: int = 0,
    hits_per_page: int = 20,
    contract_type: Optional[str] = None,
    remote: Optional[str] = None,
    experience_level_min: Optional[int] = None,
    experience_level_max: Optional[int] = None,
    salary_min: Optional[int] = None,
    profession_category: Optional[str] = None,
    organization_slug: Optional[str] = None,
    around_lat_lng: Optional[str] = None,
    around_radius_km: Optional[int] = None,
    language: str = "fr",
) -> str:
    """Search job listings on Welcome to the Jungle via Algolia.

    Args:
        query:               Free-text search (job title, skill…)
        page:                Result page (0-indexed)
        hits_per_page:       Results per page (max 30)
        contract_type:       "full_time" | "part_time" | "internship" | "apprenticeship" | "freelance" | "vie"
        remote:              "fulltime" | "partial" | "punctual" | "no"
        experience_level_min: Minimum years of experience (0, 1, 3, 5, 10)
        experience_level_max: Maximum years of experience
        salary_min:          Minimum yearly salary (EUR)
        profession_category: Profession category reference from get_job_filters()
        organization_slug:   Filter jobs for a specific company slug
        around_lat_lng:      "lat,lng" string (use autocomplete_location first)
        around_radius_km:    Search radius in km when around_lat_lng is set (default 20)
        language:            Index language variant ("fr" or "en")
    """
    await _auto_login()
    index = f"wttj_jobs_production_{language}"

    filters_parts: list[str] = []
    if contract_type:
        filters_parts.append(f'"contract_type":"{contract_type}"')
    if remote:
        filters_parts.append(f'"remote":"{remote}"')
    if profession_category:
        filters_parts.append(f'"new_profession.category_reference":"{profession_category}"')
    if organization_slug:
        filters_parts.append(f'"organization.slug":"{organization_slug}"')
    if experience_level_min is not None or experience_level_max is not None:
        lo = experience_level_min if experience_level_min is not None else 0
        hi = experience_level_max if experience_level_max is not None else 99
        filters_parts.append(f"experience_level_minimum:{lo} TO {hi}")
    if salary_min is not None:
        filters_parts.append(f"salary_yearly_minimum >= {salary_min}")

    params: dict = {
        "query": query,
        "hitsPerPage": min(hits_per_page, 30),
        "page": page,
        "analytics": True,
        "analyticsTags": json.dumps([f"language:{language}"]),
        "attributesToRetrieve": json.dumps([
            "name", "organization.name", "organization.slug", "slug",
            "contract_type", "remote", "experience_level_minimum",
            "salary_yearly_minimum", "salary_yearly_maximum", "salary_currency",
            "offices", "published_at", "new_profession", "language", "reference",
        ]),
        "attributesToHighlight": json.dumps(["name"]),
        "responseFields": json.dumps(["hits", "nbHits", "nbPages", "page", "hitsPerPage"]),
    }

    if filters_parts:
        params["filters"] = " AND ".join(f"({p})" for p in filters_parts)

    if around_lat_lng:
        params["aroundLatLng"] = around_lat_lng
        radius_m = (around_radius_km or 20) * 1000
        params["aroundRadius"] = radius_m

    payload = {"requests": [{"indexName": index, "params": urlencode(params)}]}

    resp = await _session.client.post(
        f"{ALGOLIA_DSN}/1/indexes/*/queries",
        json=payload,
        headers=_session.algolia_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("results", [{}])[0]
    return json.dumps({
        "total": result.get("nbHits", 0),
        "pages": result.get("nbPages", 0),
        "page": result.get("page", 0),
        "hits": result.get("hits", []),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Company search (Algolia)
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_companies(
    query: str = "",
    page: int = 0,
    hits_per_page: int = 20,
    sector: Optional[str] = None,
    around_lat_lng: Optional[str] = None,
    around_radius_km: Optional[int] = None,
) -> str:
    """Search companies on Welcome to the Jungle via Algolia.

    Args:
        query:           Free-text search (company name, keyword…)
        page:            Result page (0-indexed)
        hits_per_page:   Results per page (max 30)
        sector:          Industry sector name (e.g. "Tech", "Consulting / Audit")
        around_lat_lng:  "lat,lng" for geographic search
        around_radius_km: Search radius in km (default 20)
    """
    await _auto_login()

    filters_parts: list[str] = []
    if sector:
        filters_parts.append(f'"sectors_name.fr.{sector}":true')

    params: dict = {
        "query": query,
        "hitsPerPage": min(hits_per_page, 30),
        "page": page,
        "filters": 'website.reference:wttj_fr',
        "attributesToRetrieve": json.dumps([
            "name", "slug", "reference", "sectors", "offices",
            "jobs_count", "size", "logo", "descriptions",
        ]),
        "attributesToHighlight": json.dumps(["name"]),
        "responseFields": json.dumps(["hits", "nbHits", "nbPages", "page", "hitsPerPage"]),
    }

    if filters_parts:
        existing = params["filters"]
        params["filters"] = existing + " AND " + " AND ".join(f"({p})" for p in filters_parts)

    if around_lat_lng:
        params["aroundLatLng"] = around_lat_lng
        params["aroundRadius"] = (around_radius_km or 20) * 1000

    payload = {"requests": [{"indexName": COMPANY_INDEX, "params": urlencode(params)}]}

    resp = await _session.client.post(
        f"{ALGOLIA_DSN}/1/indexes/*/queries",
        json=payload,
        headers=_session.algolia_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("results", [{}])[0]
    return json.dumps({
        "total": result.get("nbHits", 0),
        "pages": result.get("nbPages", 0),
        "page": result.get("page", 0),
        "hits": result.get("hits", []),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Company detail
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_company(slug: str) -> str:
    """Get detailed information about a company by its WTTJ slug.

    Args:
        slug: Company slug (e.g. "iot-valley", "greenscope"). Visible in WTTJ URLs
              like welcometothejungle.com/companies/{slug}.
    """
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/organizations/{slug}",
        headers={**_session.api_headers(), "Accept": "application/json, application/xml"},
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Job detail
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_job(organization_slug: str, job_slug: str) -> str:
    """Get full details of a specific job posting.

    Args:
        organization_slug: Company slug (e.g. "iot-valley")
        job_slug:          Job slug as it appears in the WTTJ URL
                           (e.g. "key-account-manager_labege")
    """
    resp = await _session.client.get(
        f"{WTTJ_API}/api/v1/organizations/{organization_slug}/jobs/{job_slug}",
        headers={**_session.api_headers(), "Accept": "application/json, application/xml"},
    )
    resp.raise_for_status()
    return json.dumps(resp.json(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Company jobs (Algolia convenience wrapper)
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_company_jobs(organization_slug: str, query: str = "", page: int = 0) -> str:
    """List all open jobs for a given company.

    Args:
        organization_slug: Company slug (e.g. "iot-valley")
        query:             Optional free-text filter within company jobs
        page:              Result page (0-indexed)
    """
    return await search_jobs(
        query=query,
        page=page,
        hits_per_page=30,
        organization_slug=organization_slug,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
