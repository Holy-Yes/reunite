"""The endpoint tables in the two docs must exist in the running API. If a route is renamed, this fails."""
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
ROW = re.compile(r"^\|\s*[A-Za-z]+\s*\|\s*`(GET|POST|PATCH|DELETE|PUT)\s+(/[^`]*)`", re.M)


def norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path.split("?")[0])


def doc_endpoints(name: str) -> set[tuple[str, str]]:
    return {(m, norm(p)) for m, p in ROW.findall((DOCS / name).read_text())}


def api_endpoints(client) -> set[tuple[str, str]]:
    out = set()
    for path, ops in client.app.openapi()["paths"].items():
        for method in ops:
            out.add((method.upper(), norm(path.removeprefix("/api/v1"))))
    return out


def test_implementation_plan_endpoints_exist(client):
    planned, actual = doc_endpoints("IMPLEMENTATION_PLAN.md"), api_endpoints(client)
    assert len(planned) >= 34
    assert planned - actual == set(), f"documented but missing from the API: {sorted(planned - actual)}"


def test_website_prompt_endpoints_exist(client):
    wanted, actual = doc_endpoints("WEBSITE_PROMPT.md"), api_endpoints(client)
    assert len(wanted) >= 33
    assert wanted - actual == set(), f"the website prompt's client calls routes that do not exist: {sorted(wanted - actual)}"


def test_both_docs_describe_the_same_api(client):
    plan, site = doc_endpoints("IMPLEMENTATION_PLAN.md"), doc_endpoints("WEBSITE_PROMPT.md")
    assert plan == site, f"docs disagree: only in plan {sorted(plan - site)}; only in prompt {sorted(site - plan)}"
