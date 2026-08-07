#!/usr/bin/env python3
"""Renders light_mode.svg and dark_mode.svg for the profile README.

Everything you'd want to change by hand lives in the CONFIG block below.
GitHub stats are fetched live; run with a token for accurate numbers:

    GITHUB_TOKEN=ghp_... python3 generate_profile.py

Without a token it falls back to the unauthenticated REST API (public
counts only, no lines-of-code) so the script still produces valid SVGs.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────────────────
# CONFIG — edit this block, re-run the script, commit the SVGs.
# ─────────────────────────────────────────────────────────────────────────

USERNAME = "ishankgupta95"
TITLE = "Ishank Gupta"

CODING_SINCE = 2017
LOCATION = "Pune, India"
WORK = "Project Lead @ Persistent Systems"

SHIPPING = "panchang-ts, Dharmagya, Transmute, Onstage"
LEARNING = "Rust"

LANG_PROGRAMMING = "TypeScript, Go, Rust, Python"
LANG_SPOKEN = "English, Hindi"

HOBBY_SOFTWARE = "driver tinkering, overclocking"
HOBBY_HARDWARE = "building PCs and home servers, 3D printing"

CONTACT = [
    ("Email", "ishank1995@gmail.com"),
    ("Portfolio", "ishank.dev"),
    ("LinkedIn", "in/ishankg"),
]

# ─────────────────────────────────────────────────────────────────────────
# Layout
# ─────────────────────────────────────────────────────────────────────────

FONT_SIZE = 16
# Consolas advances 0.5498em; the @font-face size-adjust of 109% pushes that to
# ~0.60em, which is also where Menlo (macOS) and DejaVu Sans Mono (Linux) sit.
# Laying out against 0.60em keeps the two columns aligned on every platform.
CHAR_W = FONT_SIZE * 0.60
LINE_H = 20
MARGIN_X = 15
TOP_Y = 30

PANEL_W = 64         # characters of usable width in the info panel

THEMES = {
    "dark": {
        "bg": "#161b22", "fg": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff",
        "add": "#3fb950", "del": "#f85149", "dim": "#616e7f", "title": "#d2a8ff",
    },
    "light": {
        "bg": "#ffffff", "fg": "#24292f", "key": "#953800", "value": "#0a3069",
        "add": "#1a7f37", "del": "#cf222e", "dim": "#8c959f", "title": "#8250df",
    },
}

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".loc_cache.json")
API = "https://api.github.com/graphql"


# ─────────────────────────────────────────────────────────────────────────
# GitHub API
# ─────────────────────────────────────────────────────────────────────────

def _post(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": USERNAME},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read())
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def _get(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": USERNAME},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


USER_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    id
    createdAt
    followers { totalCount }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]
      includeUserRepositories: false
    ) { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        defaultBranchRef { name }
      }
    }
  }
}
"""

HISTORY_QUERY = """
query($owner: String!, $name: String!, $branch: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    ref(qualifiedName: $branch) {
      target {
        ... on Commit {
          history(author: {id: $id}, first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { oid additions deletions }
          }
        }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def fetch_authenticated(token):
    """Full stats via GraphQL. Lines of code are cached per repo."""
    repos, cursor = [], None
    user_id = created_at = None
    followers = contributed = 0

    while True:
        data = _post(USER_QUERY, {"login": USERNAME, "cursor": cursor}, token)["user"]
        user_id = data["id"]
        created_at = data["createdAt"]
        followers = data["followers"]["totalCount"]
        contributed = data["repositoriesContributedTo"]["totalCount"]
        block = data["repositories"]
        repo_total = block["totalCount"]
        repos.extend(block["nodes"])
        if not block["pageInfo"]["hasNextPage"]:
            break
        cursor = block["pageInfo"]["endCursor"]

    stars = sum(r["stargazerCount"] for r in repos)

    # Total commits across every year the account has existed.
    commits = 0
    start = int(created_at[:4])
    now = datetime.now(timezone.utc)
    for year in range(start, now.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z" if year < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        c = _post(CONTRIB_QUERY, {"login": USERNAME, "from": frm, "to": to}, token)
        c = c["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

    additions, deletions = fetch_loc(repos, user_id, token)

    return {
        "repos": repo_total, "contributed": contributed, "stars": stars,
        "commits": commits, "followers": followers,
        "additions": additions, "deletions": deletions,
    }


def fetch_loc(repos, user_id, token):
    """Sum additions/deletions across owned repos, resuming from cache."""
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}

    for repo in repos:
        branch_ref = repo.get("defaultBranchRef")
        if not branch_ref:
            continue
        name = repo["nameWithOwner"]
        owner, repo_name = name.split("/", 1)
        entry = cache.get(name, {"head": None, "additions": 0, "deletions": 0})
        seen_head = entry.get("head")

        new_add = new_del = 0
        new_head = None
        cursor = None
        done = False
        while not done:
            try:
                data = _post(HISTORY_QUERY, {
                    "owner": owner, "name": repo_name,
                    "branch": branch_ref["name"], "id": user_id, "cursor": cursor,
                }, token)
            except (urllib.error.HTTPError, RuntimeError) as exc:
                print(f"  ! skipping {name}: {exc}", file=sys.stderr)
                break

            target = (data.get("repository") or {}).get("ref") or {}
            history = (target.get("target") or {}).get("history")
            if not history:
                break

            for node in history["nodes"]:
                if new_head is None:
                    new_head = node["oid"]
                if node["oid"] == seen_head:
                    done = True
                    break
                new_add += node["additions"]
                new_del += node["deletions"]

            if done or not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]

        cache[name] = {
            "head": new_head or seen_head,
            "additions": entry["additions"] + new_add,
            "deletions": entry["deletions"] + new_del,
        }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)

    return (sum(v["additions"] for v in cache.values()),
            sum(v["deletions"] for v in cache.values()))


def fetch_public():
    """Best-effort public counts when no token is available."""
    user = _get(f"/users/{USERNAME}")
    stars = 0
    page = 1
    while True:
        batch = _get(f"/users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        stars += sum(r["stargazers_count"] for r in batch if not r["fork"])
        if len(batch) < 100:
            break
        page += 1
    return {
        "repos": user["public_repos"], "contributed": 0, "stars": stars,
        "commits": 0, "followers": user["followers"],
        "additions": 0, "deletions": 0,
    }


def previous_stats():
    """Re-read the numbers already baked into dark_mode.svg, so a failed
    fetch degrades to stale-but-real rather than zeroes."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "dark_mode.svg")) as f:
            svg = f.read()
    except OSError:
        return None
    found = re.search(r"<!--stats (\{.*?\}) -->", svg)
    return json.loads(found.group(1)) if found else None


# ─────────────────────────────────────────────────────────────────────────
# SVG rendering
# ─────────────────────────────────────────────────────────────────────────

def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def span(text, cls=None):
    if not text:
        return ""
    return f'<tspan class="{cls}">{esc(text)}</tspan>' if cls else esc(text)


def line(x, y, segments):
    inner = "".join(span(t, c) for t, c in segments)
    return f'<tspan x="{x}" y="{y}">{inner}</tspan>'


def comma(n):
    return f"{n:,}"


def build_panel(stats):
    """The neofetch-style right-hand panel, as a list of segment-lists."""
    rows = []

    def header(text):
        rows.append([])
        rows.append([("- ", "dim"), (text, "title")])
        rows.append([("-" + "─" * (PANEL_W - 1), "dim")])

    def field(key, value):
        # ".Key: " + dots + " " + value, right-aligned to PANEL_W
        dots = "." * max(PANEL_W - len(key) - 4 - len(value), 1)
        rows.append([(".", "dim"), (key, "key"), (": ", "dim"),
                     (dots + " ", "dim"), (value, "value")])

    def blank():
        rows.append([])

    rows.append([(TITLE, "title")])
    rows.append([("-" + "─" * (PANEL_W - 1), "dim")])

    years = datetime.now(timezone.utc).year - CODING_SINCE
    field("Coding since", f"{CODING_SINCE}  ({years} years)")
    field("Location", LOCATION)
    field("Work", WORK)
    field("Shipping", SHIPPING)
    field("Learning", LEARNING)
    blank()
    field("Languages.Programming", LANG_PROGRAMMING)
    field("Languages.Spoken", LANG_SPOKEN)
    blank()
    field("Hobbies.Software", HOBBY_SOFTWARE)
    field("Hobbies.Hardware", HOBBY_HARDWARE)

    header("Contact")
    for key, value in CONTACT:
        field(key, value)

    header("GitHub Stats")
    repos, contributed = comma(stats["repos"]), comma(stats["contributed"])

    # ".Repos: " dots " " repos "  {Contributed: " n "}"
    dots = "." * max(PANEL_W - 26 - len(repos) - len(contributed), 1)
    rows.append([
        (".", "dim"), ("Repos", "key"), (": ", "dim"),
        (dots + " ", "dim"), (repos, "value"),
        ("  {", "dim"), ("Contributed", "key"), (": ", "dim"), (contributed, "value"),
        ("}", "dim"),
    ])
    field("Commits", comma(stats["commits"]))
    # ".Lines of Code: " dots " " net "  (" add "++, " del "--)"
    net = comma(stats["additions"] - stats["deletions"])
    add, dele = comma(stats["additions"]), comma(stats["deletions"])
    dots = "." * max(PANEL_W - 27 - len(net) - len(add) - len(dele), 1)
    rows.append([
        (".", "dim"), ("Lines of Code", "key"), (": ", "dim"), (dots + " ", "dim"),
        (net, "value"),
        ("  (", "dim"), (add, "add"), ("++", "add"),
        (", ", "dim"), (dele, "del"), ("--", "del"), (")", "dim"),
    ])
    return rows


def check_widths(panel):
    """A value longer than PANEL_W silently runs off the edge of the SVG,
    so fail loudly instead and say how much room is needed."""
    over = []
    for segs in panel:
        n = sum(len(text) for text, _ in segs)
        if n > PANEL_W:
            over.append((n, "".join(text for text, _ in segs)))
    if over:
        need = max(n for n, _ in over)
        for n, text in over:
            print(f"  ! row is {n} chars, PANEL_W is {PANEL_W}: {text}", file=sys.stderr)
        raise SystemExit(
            f"Panel content overflows. Shorten the values above, or set "
            f"PANEL_W = {need} (currently {PANEL_W})."
        )


def render(theme_name, stats):
    t = THEMES[theme_name]
    panel = build_panel(stats)
    check_widths(panel)

    width = round(2 * MARGIN_X + PANEL_W * CHAR_W)
    height = TOP_Y + len(panel) * LINE_H

    panel_svg = "\n".join(
        line(MARGIN_X, TOP_Y + i * LINE_H, segs) for i, segs in enumerate(panel)
    )

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,Menlo,DejaVu Sans Mono,monospace" width="{width}px" height="{height}px" font-size="{FONT_SIZE}px">
<style>
@font-face {{
src: local('Consolas');
font-family: 'ConsolasFallback';
font-display: swap;
size-adjust: 109%;
}}
.key {{fill: {t['key']};}}
.value {{fill: {t['value']};}}
.add {{fill: {t['add']};}}
.del {{fill: {t['del']};}}
.dim {{fill: {t['dim']};}}
.title {{fill: {t['title']};}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{width}px" height="{height}px" fill="{t['bg']}" rx="15"/>
<text x="{MARGIN_X}" y="{TOP_Y}" fill="{t['fg']}" xml:space="preserve">
{panel_svg}
</text>
<!--stats {json.dumps(stats, sort_keys=True)} -->
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN")
    try:
        if token:
            stats = fetch_authenticated(token)
        else:
            print("No GITHUB_TOKEN set — using public counts only.", file=sys.stderr)
            stats = fetch_public()
    except Exception as exc:  # network, rate limit, bad token
        print(f"Stats fetch failed ({exc}); reusing last known numbers.", file=sys.stderr)
        stats = previous_stats()
        if stats is None:
            stats = {"repos": 0, "contributed": 0, "stars": 0, "commits": 0,
                     "followers": 0, "additions": 0, "deletions": 0}

    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("dark", "light"):
        path = os.path.join(here, f"{name}_mode.svg")
        with open(path, "w") as f:
            f.write(render(name, stats))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
