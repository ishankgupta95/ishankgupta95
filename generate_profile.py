#!/usr/bin/env python3
"""Renders light_mode.svg and dark_mode.svg for the profile README.

The panel is drawn as an instrument readout: three live gauges, a 52-week
activity trace, and one row per project ("drive bay") carrying that repo's
real line count and last-write time. Every number on it is measured, not
decorative -- see DERIVE for exactly how each one is defined.

Run with a token for the full set; without one it degrades to public REST
counts, and if the network fails entirely it re-reads the numbers already
baked into dark_mode.svg so a bad morning leaves stale-but-true output.

    GITHUB_TOKEN=ghp_... python3 generate_profile.py
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
NAME = "ISHANK GUPTA"
NODE = "pune-01"
ROLE = "PROJECT LEAD @ PERSISTENT"
# Only used if the API can't tell us when the account was opened; UPTIME is
# otherwise measured from the real createdAt.
FALLBACK_SINCE = datetime(2016, 1, 15, tzinfo=timezone.utc)

# Drive bays, top to bottom. `slug` keys into the LOC cache and the live repo
# list. `stack` is declared here rather than read from the API because three of
# these repos are private -- an unauthenticated run would otherwise blank the
# column out.
BAYS = [
    {"label": "panchang-ts", "slug": "ishankgupta95/panchang-ts",
     "stack": "TypeScript", "note": "ephemeris core", "status": "npm"},
    {"label": "dharmagya", "slug": "ishankgupta95/dharmagya",
     "stack": "React Native", "note": "ios · android", "status": "app store"},
    {"label": "transmute", "slug": "ishankgupta95/transmute",
     "stack": "WebAssembly", "note": "browser only", "status": "live"},
    {"label": "onstage", "slug": "ishankgupta95/OnStage",
     "stack": "Canvas", "note": "store assets", "status": "live"},
]

# Published packages whose install counts stand for reach. npm's download API
# is public, so this is the one reading that never needs a token.
NPM_PACKAGES = ["panchang-ts"]
PLATFORMS = "npm · ios · android · web"

LINKS = "ishank.dev  ·  in/ishankg  ·  ishank1995@gmail.com"

# Chip colours for both stacks and languages. Anything unlisted gets a stable
# generated hue, so a new language never collides with an existing one.
CHIP_COLORS = {
    "TypeScript": "#3178c6", "JavaScript": "#f1e05a", "Go": "#00add8",
    "Rust": "#dea584", "Python": "#3572a5", "Java": "#b07219",
    "Kotlin": "#a97bff", "Swift": "#f05138", "Objective-C": "#438eff",
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Ruby": "#701516",
    "PHP": "#4f5d95", "Dart": "#00b4ab", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "SCSS": "#c6538c",
    "Makefile": "#427819", "Dockerfile": "#384d54", "Vue": "#41b883",
    "React Native": "#61dafb", "WebAssembly": "#654ff0",
    "Next.js": "#8b8b8b", "Canvas": "#e0a03a",
}


def chip_color(name):
    if name in CHIP_COLORS:
        return CHIP_COLORS[name]
    return f"hsl({sum(ord(c) * 7 for c in name) % 360}, 52%, 56%)"

# ─────────────────────────────────────────────────────────────────────────
# Layout — one 840px-wide instrument face.
# ─────────────────────────────────────────────────────────────────────────

W = 840
PAD = 22
FONT = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,"
        "'DejaVu Sans Mono',monospace")

HEADER_H = 58
GAUGE_Y, GAUGE_H, GAUGE_GAP = 78, 106, 14
GAUGE_W = (W - 2 * PAD - 2 * GAUGE_GAP) / 3

LANGS_Y, LANGS_H = 208, 66           # label strip, stacked bar, legend
LANG_BAR_Y, LANG_BAR_H = LANGS_Y + 22, 16

BAYS_Y, BAY_ROW = LANGS_Y + LANGS_H + 20, 25
BAYS_H = 16 + len(BAYS) * BAY_ROW

FOOT_Y = BAYS_Y + BAYS_H + 20
H = FOOT_Y + 30

THEMES = {
    "dark": {
        "bg": "#0b0f14", "panel": "#111820", "edge": "#1d2833", "grid": "#19212b",
        "fg": "#d6dee7", "dim": "#66788a", "faint": "#33414f",
        "ok": "#35c46a", "warn": "#e0a03a", "crit": "#f0603f", "accent": "#4fc3d9",
    },
    "light": {
        "bg": "#ffffff", "panel": "#f6f8fa", "edge": "#d9e0e8", "grid": "#e9eef3",
        "fg": "#131a22", "dim": "#5f6d7c", "faint": "#c2ccd6",
        "ok": "#1a7f37", "warn": "#9a6700", "crit": "#cf222e", "accent": "#0d7d92",
    },
}

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".loc_cache.json")
HERE = os.path.dirname(os.path.abspath(__file__))
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
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        defaultBranchRef { name }
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
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
    repos, cursor = [], None
    user_id = created_at = None
    repo_total = 0

    while True:
        data = _post(USER_QUERY, {"login": USERNAME, "cursor": cursor}, token)["user"]
        user_id = data["id"]
        created_at = data["createdAt"]
        block = data["repositories"]
        repo_total = block["totalCount"]
        repos.extend(block["nodes"])
        if not block["pageInfo"]["hasNextPage"]:
            break
        cursor = block["pageInfo"]["endCursor"]

    now = datetime.now(timezone.utc)

    # Lifetime commits, one contributionsCollection window per year.
    commits = 0
    for year in range(int(created_at[:4]), now.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z" if year < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        c = _post(CONTRIB_QUERY, {"login": USERNAME, "from": frm, "to": to}, token)
        c = c["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]

    additions, deletions = fetch_loc(repos, user_id, token)

    return {
        "repos": repo_total, "commits": commits,
        "additions": additions, "deletions": deletions,
        "created_at": created_at,
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
            # Kept per repo so private repos still count toward the language
            # mix on runs that can't see them.
            "languages": {e["node"]["name"]: e["size"]
                          for e in (repo.get("languages") or {}).get("edges") or []}
                         or entry.get("languages", {}),
        }

    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    return (sum(v["additions"] for v in cache.values()),
            sum(v["deletions"] for v in cache.values()))


def fetch_npm(packages):
    """Weekly install counts for the published packages, summed. Runs on its
    own request path so a GitHub outage never costs us this reading."""
    daily = {}
    for package in packages:
        req = urllib.request.Request(
            f"https://api.npmjs.org/downloads/range/last-year/{package}",
            headers={"Accept": "application/json", "User-Agent": USERNAME})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                points = json.loads(r.read()).get("downloads", [])
        except Exception as exc:
            print(f"  ! npm downloads for {package}: {exc}", file=sys.stderr)
            continue
        for point in points:
            daily[point["day"]] = daily.get(point["day"], 0) + point["downloads"]

    series = sorted(daily.items())
    starts = range(0, max(len(series) - 6, 0), 7)
    weeks = [sum(v for _, v in series[i:i + 7]) for i in starts]

    # Drop the flat stretch before the first release: those weeks are zero
    # because the package didn't exist yet, and showing them reads as a lull.
    # The total stays a true 12-month figure -- only the plotted window moves.
    first = next((i for i, v in enumerate(weeks) if v), 0)
    return {"weeks": weeks[first:], "total": sum(daily.values())}


def fetch_public():
    """Best-effort public counts when no token is available."""
    user = _get(f"/users/{USERNAME}")
    names, page = [], 1
    while True:
        batch = _get(f"/users/{USERNAME}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        names += [r["full_name"] for r in batch if not r["fork"]]
        if len(batch) < 100:
            break
        page += 1
    # Refresh language bytes for whatever is public; cached entries for the
    # private repos survive untouched.
    cache = load_cache()
    for name in names:
        try:
            langs = _get(f"/repos/{name}/languages")
        except Exception as exc:
            print(f"  ! languages for {name}: {exc}", file=sys.stderr)
            continue
        if langs:
            cache.setdefault(name, {"head": None, "additions": 0, "deletions": 0})
            cache[name]["languages"] = langs
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)

    return {
        "repos": user["public_repos"], "commits": 0,
        "additions": sum(v["additions"] for v in cache.values()),
        "deletions": sum(v["deletions"] for v in cache.values()),
        "created_at": user["created_at"],
    }


# ───────────────────────────────────────────────────────────────────────
# Fallbacks — where readings come from when the API can't answer.
# ───────────────────────────────────────────────────────────────────────

# Readings the unauthenticated REST path simply cannot measure: commit history
# and the contribution calendar both need a token. Rather than print zeroes for
# them, carry the last real value forward.
# Readings no offline source can reconstruct. The language mix and the drive
# bays are deliberately absent: cache_readings() rebuilds those from disk.
STALE_OK = ("commits", "additions", "deletions", "npm_weeks", "npm_total")


def previous_readings():
    """Re-read the readings already baked into dark_mode.svg, so a failed
    fetch degrades to stale-but-real rather than a panel full of zeroes.
    Also understands the older <!--stats--> block this panel replaced."""
    try:
        with open(os.path.join(HERE, "dark_mode.svg")) as f:
            svg = f.read()
    except OSError:
        return None
    found = re.search(r"<!--readings (\{.*?\}) -->", svg, re.S)
    if found:
        return json.loads(found.group(1))
    legacy = re.search(r"<!--stats (\{.*?\}) -->", svg, re.S)
    return json.loads(legacy.group(1)) if legacy else None


def backfill(readings, prev):
    """Fill in only the readings this run could not measure at all."""
    for key in STALE_OK:
        if not readings.get(key) and prev.get(key):
            readings[key] = prev[key]
    return readings


def normalize(readings):
    """Guarantee every key the renderer reads, so a fallback to an older or
    partial readings block still draws a complete panel."""
    now = datetime.now(timezone.utc)
    uptime = now - FALLBACK_SINCE
    defaults = {
        "langs": [], "lang_other": 0, "attributed": 0,
        "npm_weeks": [], "npm_total": 0,
        "npm_packages": NPM_PACKAGES, "shipped": len(BAYS),
        "uptime_y": uptime.days // 365, "uptime_d": uptime.days % 365,
        "repos": 0, "commits": 0, "additions": 0, "deletions": 0,
        "stamp": now.strftime("%Y-%m-%d %H:%M UTC"),
    }
    for key, value in defaults.items():
        readings.setdefault(key, value)
    if not readings.get("bays"):
        readings.update(cache_readings())
    return readings


# ─────────────────────────────────────────────────────────────────────────
# DERIVE — turn raw API data into the numbers actually printed on the panel.
# ─────────────────────────────────────────────────────────────────────────

def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def cache_readings():
    """Everything the on-disk LOC cache can answer by itself. No network is
    involved, so these stay correct even on a run where every fetch failed."""
    cache = load_cache()
    langs, lang_other, attributed = language_lines(cache)
    return {
        "langs": langs, "lang_other": lang_other, "attributed": attributed,
        "bays": [{
            "label": bay["label"], "note": bay["note"], "stack": bay["stack"],
            "status": bay["status"],
            "loc": cache.get(bay["slug"], {}).get("additions", 0),
        } for bay in BAYS],
    }


def language_lines(cache, top=5):
    """Split each repo's authored additions across the languages that repo is
    written in, weighted by its byte composition, and total by language.

    This is an estimate and nothing else will do: GitHub reports which lines a
    commit touched, not which language they were in. Repos whose composition
    we've never seen contribute nothing, so the panel reports how much of the
    line count it actually managed to attribute rather than implying it's all
    accounted for.

    The top `top` languages are named and everything below them rolls into
    "other". Small entries are fine to name because the legend prints the exact
    line count beside each one, so a few hundred lines reads as a few hundred
    lines rather than as a claim of fluency."""
    totals = {}
    attributed = 0
    for entry in cache.values():
        added = entry.get("additions", 0)
        sizes = entry.get("languages") or {}
        total_bytes = sum(sizes.values())
        if not added or not total_bytes:
            continue
        attributed += added
        for name, size in sizes.items():
            totals[name] = totals.get(name, 0) + added * size / total_bytes

    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    head = [[name, round(v)] for name, v in ranked[:top]]
    other = round(sum(v for _, v in ranked[top:]))
    return head, other, attributed


def derive(raw):
    """Every reading on the panel, with its definition stated once, here.

    Nothing in here measures how often he shows up. Cadence readings (commits
    per day, load against a personal peak, streaks) punish someone who has a
    day job and builds in bursts -- they'd dip in the very week an App Store
    release went out, because releases don't come with daily commits. What the
    panel reports instead is what exists because of the work: lines written,
    what they're written in, what shipped, and whether anyone uses it.
    """
    now = datetime.now(timezone.utc)

    # UPTIME is the age of the account, which is what "node uptime" should mean.
    since = datetime.fromisoformat(
        (raw.get("created_at") or FALLBACK_SINCE.isoformat()).replace("Z", "+00:00"))
    uptime = now - since

    npm = raw.get("npm") or {}

    readings = {
        "npm_weeks": npm.get("weeks", []), "npm_total": npm.get("total", 0),
        "npm_packages": NPM_PACKAGES,
        "shipped": len(BAYS),
        "uptime_y": uptime.days // 365, "uptime_d": uptime.days % 365,
        "repos": raw["repos"], "commits": raw["commits"],
        "additions": raw["additions"], "deletions": raw["deletions"],
        "stamp": now.strftime("%Y-%m-%d %H:%M UTC"),
    }
    readings.update(cache_readings())
    return readings


# ─────────────────────────────────────────────────────────────────────────
# SVG primitives
# ─────────────────────────────────────────────────────────────────────────

def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, s, size=11, fill="fg", anchor="start", weight=400, track=0, opacity=None):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    t = f' letter-spacing="{track}"' if track else ""
    w = f' font-weight="{weight}"' if weight != 400 else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
            f'class="{fill}"{a}{t}{w}{o}>{esc(s)}</text>')


def rect(x, y, w, h, fill=None, stroke=None, r=0, opacity=None):
    f = f' class="{fill}"' if fill else ' fill="none"'
    s = f' stroke="{stroke}"' if stroke else ""
    rr = f' rx="{r}"' if r else ""
    o = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"{f}{s}{rr}{o}/>'


def hline(x1, x2, y, cls, opacity=None):
    o = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'class="s-{cls}"{o}/>')


def comma(n):
    return f"{n:,}"


def kilo(n):
    """182441 -> '182.4k'; small numbers stay exact."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ─────────────────────────────────────────────────────────────────────────
# Panel sections
# ─────────────────────────────────────────────────────────────────────────

def draw_header(r, t):
    out = [rect(0, 0, W, HEADER_H, fill="f-panel")]
    out.append(hline(0, W, HEADER_H - 0.5, "edge"))
    out.append(txt(PAD, 27, NAME, size=17, weight=600, track=2.4))
    out.append(txt(PAD, 43, ROLE, size=9, fill="f-dim", track=1.6))

    # Right-hand status cluster, laid out right-to-left.
    x = W - PAD
    out.append(txt(x, 40, "ONLINE", size=9, fill="f-ok", anchor="end", track=1.4))
    out.append(f'<circle cx="{x - 45:.1f}" cy="{36.5}" r="3" class="f-ok" '
               f'id="led"/>')
    out.append(txt(x, 24, f"{r['uptime_y']}y {r['uptime_d']:03d}d",
                   size=11, anchor="end"))
    out.append(txt(x - 78, 24, "UPTIME", size=9, fill="f-dim", anchor="end", track=1.2))
    out.append(txt(x - 78, 40, f"node {NODE}", size=9, fill="f-dim",
                   anchor="end", track=1.2))
    return out


CELLS, CELL_GAP, METER_Y, METER_H = 24, 3, GAUGE_Y + 62, 13


def draw_card(x, label, value, unit, note, meter, t):
    """One card: caption, big reading, unit, meter, footnote.

    `meter` is ("hist", [values]) for a one-cell-per-period histogram, or
    ("mix", [(value, colour), ...]) for a proportional stacked bar.
    """
    y = GAUGE_Y
    out = [rect(x, y, GAUGE_W, GAUGE_H, fill="f-panel", stroke=t["edge"], r=6)]
    out.append(txt(x + 14, y + 20, label, size=9, fill="f-dim", track=1.8))
    out.append(txt(x + 14, y + 52, value, size=27, weight=600))
    if unit:
        # Advance of the 27px monospace reading, then the unit beside it.
        out.append(txt(x + len(value) * 16.2 + 20, y + 52, unit, size=10,
                       fill="f-dim"))

    span = GAUGE_W - 28
    kind, data = meter
    if kind == "hist":
        cw = (span - CELL_GAP * (CELLS - 1)) / CELLS
        top = max(max(data, default=0), 1)
        cells = ([0] * (CELLS - len(data)) + list(data))[-CELLS:]
        for i, v in enumerate(cells):
            h = max(METER_H * v / top, 2)
            out.append(rect(x + 14 + i * (cw + CELL_GAP), METER_Y + METER_H - h,
                            cw, h, fill="f-accent" if v else "f-faint",
                            opacity=None if v else 0.55))
    else:
        total = sum(v for v, _ in data) or 1
        bx = float(x + 14)
        for value_, color in data:
            w = span * value_ / total
            out.append(f'<rect x="{bx:.1f}" y="{METER_Y + 4}" '
                       f'width="{w + 0.5:.1f}" height="9" fill="{color}"/>')
            bx += w

    out.append(txt(x + 14, y + 93, note, size=9, fill="f-dim"))
    return out

def draw_cards(r, t):
    """Three totals. Each only grows, so a quiet month never reads as decline."""
    out = []

    # How much survived: written against erased, in proportion.
    written, erased = r["additions"], r["deletions"]
    out += draw_card(PAD, "LINES WRITTEN", comma(written), "",
                     f"−{comma(erased)} erased · {r['repos']} repos",
                     ("mix", [(written, t["ok"]), (erased, t["crit"])]), t)

    packages = " · ".join(r["npm_packages"]) or "npm"
    out += draw_card(PAD + GAUGE_W + GAUGE_GAP, "NPM INSTALLS",
                     comma(r["npm_total"]), "/yr",
                     f"{packages} · last 12 months",
                     ("hist", r["npm_weeks"][-CELLS:]), t)

    # One equal segment per project, coloured like its drive bay -- this card
    # is a count, so sizing by lines would hide the smaller ones entirely.
    mix = [(1, chip_color(bay["stack"])) for bay in r["bays"]]
    out += draw_card(PAD + 2 * (GAUGE_W + GAUGE_GAP), "SHIPPED",
                     str(r["shipped"]), "projects", PLATFORMS, ("mix", mix), t)
    return out


def draw_langs(r, t):
    """Stacked bar of authored lines by language, with a packed legend."""
    x0, x1 = PAD, W - PAD
    out = [txt(x0, LANGS_Y + 12, "LANGUAGE MIX", size=9, fill="f-dim", track=1.8)]

    segments = [(name, value) for name, value in r["langs"] if value > 0]
    total = sum(v for _, v in segments) + r["lang_other"]
    if not total:
        out.append(txt(x0, LANGS_Y + 38, "no language data", size=10, fill="f-dim"))
        return out

    # Say plainly how much of the line count this actually accounts for --
    # repos whose composition we've never seen are simply absent.
    out.append(txt(x1, LANGS_Y + 12,
                   f"{kilo(r['attributed'])} OF {kilo(r['additions'])} LINES ATTRIBUTED",
                   size=9, fill="f-dim", anchor="end", track=1.2))

    out.append(f'<clipPath id="langbar"><rect x="{x0}" y="{LANG_BAR_Y}" '
               f'width="{x1 - x0}" height="{LANG_BAR_H}" rx="3"/></clipPath>')
    out.append('<g clip-path="url(#langbar)">')
    x = float(x0)
    for name, value in segments:
        w = (x1 - x0) * value / total
        out.append(f'<rect x="{x:.1f}" y="{LANG_BAR_Y}" width="{w + 0.5:.1f}" '
                   f'height="{LANG_BAR_H}" fill="{chip_color(name)}"/>')
        x += w
    out.append(rect(x, LANG_BAR_Y, x1 - x, LANG_BAR_H, fill="f-faint", opacity=0.6))
    out.append('</g>')

    entries = [(name, kilo(value), chip_color(name)) for name, value in segments]
    if r["lang_other"]:
        entries.append(("other", kilo(r["lang_other"]), t["faint"]))

    lx = float(x0)
    for name, value, color in entries:
        label = f"{name} {value}"
        out.append(f'<circle cx="{lx + 3.5:.1f}" cy="{LANGS_Y + 52.5:.1f}" '
                   f'r="3.2" fill="{color}"/>')
        out.append(txt(lx + 13, LANGS_Y + 56, label, size=10, fill="f-dim"))
        lx += 13 + advance(label, 10) + 20
    return out


# Right edge of the lines column, bar width, and the gutter between the
# bar and the widest figure it can sit next to ("304.8k").
LOC_COL, BAR_W, BAR_GAP = 96, 130, 48


def draw_bays(r, t):
    """One row per project. Deliberately no "last write" column: these ship and
    then stay shipped, and a recency reading would score finished work as rot."""
    x0, x1 = PAD, W - PAD
    out = [txt(x0, BAYS_Y + 10, "DRIVE BAYS", size=9, fill="f-dim", track=1.8)]
    out.append(txt(x1 - LOC_COL, BAYS_Y + 10, "LINES", size=9,
                   fill="f-dim", anchor="end", track=1.2))
    out.append(txt(x1, BAYS_Y + 10, "STATUS", size=9,
                   fill="f-dim", anchor="end", track=1.2))
    out.append(hline(x0, x1, BAYS_Y + 18, "edge"))

    top = max((bay["loc"] for bay in r["bays"]), default=1) or 1
    for i, bay in enumerate(r["bays"]):
        y = BAYS_Y + 16 + (i + 1) * BAY_ROW - 8
        out.append(txt(x0, y, f"{i}", size=9, fill="f-dim"))
        out.append(txt(x0 + 18, y, bay["label"], size=12))

        out.append(f'<circle cx="{x0 + 180:.1f}" cy="{y - 4:.1f}" r="3.2" '
                   f'fill="{chip_color(bay["stack"])}"/>')
        out.append(txt(x0 + 190, y, bay["stack"], size=10, fill="f-dim"))
        out.append(txt(x0 + 300, y, bay["note"], size=10, fill="f-dim", opacity=0.75))

        bx = x1 - LOC_COL - BAR_GAP - BAR_W
        out.append(rect(bx, y - 8, BAR_W, 6, fill="f-faint", opacity=0.5, r=1))
        if bay["loc"]:
            out.append(rect(bx, y - 8, BAR_W * bay["loc"] / top, 6,
                            fill="f-accent", r=1))
        out.append(txt(x1 - LOC_COL, y, kilo(bay["loc"]) if bay["loc"] else "—",
                       size=11, anchor="end"))
        out.append(txt(x1, y, bay["status"], size=11, fill="f-dim", anchor="end"))
    return out

def draw_footer(r, t):
    x0, x1 = PAD, W - PAD
    out = [hline(x0, x1, FOOT_Y - 6, "edge")]
    totals = (f"{comma(r['commits'])} commits · {r['repos']} repos · "
              f"{r['uptime_y']} years")
    out.append(txt(x0, FOOT_Y + 12, totals, size=10, fill="f-dim"))
    out.append(txt(x1, FOOT_Y + 12, LINKS, size=10, fill="f-dim", anchor="end"))
    return out

def advance(text, size):
    """Width of a monospace run. Every face in FONT sits at 0.6em."""
    return len(text) * size * 0.6


def check_fit(r):
    """A character-cell layout makes overflow obvious; anchored text just
    silently overlaps. Check the columns that can actually collide and fail
    loudly, rather than shipping a panel with numbers on top of each other."""
    x1 = W - PAD
    problems = []

    totals = (f"{comma(r['commits'])} commits · {r['repos']} repos · "
              f"{r['uptime_y']} years")
    if PAD + advance(totals, 10) + 24 > x1 - advance(LINKS, 10):
        problems.append(f"footer totals and LINKS collide: {LINKS!r}")

    note_limit = x1 - LOC_COL - BAR_GAP - BAR_W - 12
    for bay in r["bays"]:
        if PAD + 190 + advance(bay["stack"], 10) > PAD + 300 - 8:
            problems.append(f"stack overruns its column: {bay['stack']!r}")
        if PAD + 300 + advance(bay["note"], 10) > note_limit:
            problems.append(f"note runs into the bar: {bay['note']!r}")
        if advance(bay["status"], 11) + 12 > LOC_COL:
            problems.append(f"status overruns the lines column: {bay['status']!r}")

    if PAD + advance(NAME, 17) + advance(NAME, 17) * 0.14 > x1 - 200:
        problems.append(f"NAME crowds the status cluster: {NAME!r}")

    legend = sum(13 + advance(f"{n} {kilo(v)}", 10) + 20 for n, v in r["langs"])
    if r["lang_other"]:
        legend += 13 + advance(f"other {kilo(r['lang_other'])}", 10) + 20
    if legend > x1 - PAD:
        problems.append(f"language legend needs {legend:.0f}px of {x1 - PAD}px")

    if problems:
        for problem in problems:
            print(f"  ! {problem}", file=sys.stderr)
        raise SystemExit("Panel content overflows; shorten the values above.")


def render(theme_name, r):
    t = THEMES[theme_name]
    body = []
    body += draw_header(r, t)
    body += draw_cards(r, t)
    body += draw_langs(r, t)
    body += draw_bays(r, t)
    body += draw_footer(r, t)

    fills = "\n".join(f".f-{k} {{fill: {v};}}" for k, v in t.items())
    strokes = "\n".join(f".s-{k} {{stroke: {v};}}" for k, v in t.items())

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
     viewBox="0 0 {W} {H}" font-family="{FONT}" role="img"
     aria-label="{esc(NAME)} — GitHub activity readout">
<title>{esc(NAME)} — GitHub activity readout</title>
<style>
text {{fill: {t['fg']};}}
{fills}
{strokes}
line {{stroke-width: 1;}}
#led {{animation: pulse 2.4s ease-in-out infinite;}}
@keyframes pulse {{0%,100% {{opacity: 1;}} 50% {{opacity: 0.25;}}}}
@media (prefers-reduced-motion: reduce) {{#led {{animation: none;}}}}
</style>
<rect width="{W}" height="{H}" class="f-bg" rx="10"/>
{chr(10).join(body)}
<!--readings {json.dumps(r, sort_keys=True)} -->
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("ACCESS_TOKEN")
    prev = previous_readings()
    npm = fetch_npm(NPM_PACKAGES)
    try:
        if token:
            raw = fetch_authenticated(token)
        else:
            print("No GITHUB_TOKEN set — public counts only; commit history "
                  "and the activity trace will carry over.", file=sys.stderr)
            raw = fetch_public()
        raw["npm"] = npm
        readings = derive(raw)
        if prev:
            readings = backfill(readings, prev)
    except Exception as exc:  # network, rate limit, bad token
        print(f"Fetch failed ({exc}); reusing last known readings.", file=sys.stderr)
        readings = prev
        if readings is None:
            raise SystemExit("No cached readings in dark_mode.svg to fall back on.")
        # A failed fetch is no reason to serve a stale language mix.
        readings.update(cache_readings())

    readings = normalize(readings)
    check_fit(readings)

    # Render both fully before touching disk. Opening for write truncates
    # immediately, so rendering straight into the file means any error empties
    # dark_mode.svg -- which is where previous_readings() looks, so one bad
    # render would silently destroy the fallback for every run after it.
    pages = {name: render(name, readings) for name in ("dark", "light")}
    for name, svg in pages.items():
        path = os.path.join(HERE, f"{name}_mode.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
