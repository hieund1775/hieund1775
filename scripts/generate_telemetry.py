#!/usr/bin/env python3
"""Build GitHub Profile telemetry as local, theme-aware SVG files.

Data is fetched from the authenticated GitHub GraphQL public contribution
calendar and the public GitHub REST repository/language APIs. The resulting
figures are real GitHub counts, not an estimate of skill or total all-time work.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

GQL = """
query ProfileTelemetry($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""

THEMES = {
    "dark": {
        "bg": "#090F1D", "panel": "#101D31", "surface": "#14243A", "stroke": "#294364",
        "text": "#E9F2FC", "muted": "#A0B1C7", "faint": "#6D839F", "track": "#243852",
        "cyan": "#67E8F9", "violet": "#B39AFF", "blue": "#68A7FF", "other": "#5A779D",
    },
    "light": {
        "bg": "#FFFFFF", "panel": "#F8FAFE", "surface": "#EDF4FC", "stroke": "#C5D5E9",
        "text": "#12233B", "muted": "#475B76", "faint": "#697F9B", "track": "#D9E5F2",
        "cyan": "#087E9D", "violet": "#7351D3", "blue": "#2563B8", "other": "#7F93B0",
    },
}

COLORS = ("cyan", "violet", "blue", "other")


def request_json(url: str, token: str, payload: dict | None = None) -> dict | list:
    headers = {
        "User-Agent": "hieund1775-profile-telemetry",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urlopen(req, timeout=35) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read(1024).decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API unreachable: {exc.reason}") from exc


def count_streaks(days: dict[str, int], today: date) -> tuple[int, int]:
    """Current streak stays active if a contribution was made yesterday.

    Longest streak is limited to the visible ~365-day contribution window.
    """
    ordered = sorted((date.fromisoformat(k), v) for k, v in days.items() if date.fromisoformat(k) <= today)
    longest = 0
    run = 0
    prev = None
    for day, value in ordered:
        if value > 0:
            run = run + 1 if prev == day - timedelta(days=1) else 1
            longest = max(longest, run)
            prev = day
        else:
            run = 0
            prev = None

    probe = today
    if days.get(probe.isoformat(), 0) <= 0:
        probe = today - timedelta(days=1)
    current = 0
    while days.get(probe.isoformat(), 0) > 0:
        current += 1
        probe -= timedelta(days=1)
    return current, longest


def collect_live(username: str, token: str) -> dict:
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required. Configure it in the GitHub Actions workflow.")

    now = datetime.now(timezone.utc)
    from_time = now - timedelta(days=365)
    query = request_json(
        "https://api.github.com/graphql",
        token,
        {"query": GQL, "variables": {
            "login": username,
            "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }},
    )
    if query.get("errors"):
        raise RuntimeError("GitHub GraphQL returned errors: " + json.dumps(query["errors"])[:700])
    user = (query.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"Could not find GitHub user {username!r} in GraphQL response")

    coll = user["contributionsCollection"]
    cal = coll["contributionCalendar"]
    days = {d["date"]: int(d["contributionCount"])
            for w in cal["weeks"] for d in w["contributionDays"]}
    local_today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    current, longest = count_streaks(days, local_today)

    languages = Counter()
    stars = 0
    repo_count = 0
    # Public repositories only, excluding forks and archived copies.
    for page in range(1, 21):
        repos = request_json(
            f"https://api.github.com/users/{quote(username)}/repos?type=owner&per_page=100&page={page}",
            token,
        )
        if not isinstance(repos, list):
            raise RuntimeError("Unexpected repository list response")
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            repo_count += 1
            stars += int(repo.get("stargazers_count", 0))
            lang = request_json(
                f"https://api.github.com/repos/{quote(username)}/{quote(repo['name'])}/languages",
                token,
            )
            languages.update({k: int(v) for k, v in lang.items()})
        if len(repos) < 100:
            break
    else:
        raise RuntimeError("Exceeded 2000 public repositories; pagination limit needs increasing")

    return {
        "username": username,
        "as_of": local_today.isoformat(),
        "contributions": int(cal["totalContributions"]),
        "current_streak": current,
        "longest_streak": longest,
        "commits": int(coll["totalCommitContributions"]),
        "pull_requests": int(coll["totalPullRequestContributions"]),
        "issues": int(coll["totalIssueContributions"]),
        "reviews": int(coll["totalPullRequestReviewContributions"]),
        "stars": stars,
        "public_repos": repo_count,
        "languages": dict(languages),
    }


def t(x, y, s, *, size=15, color="#ffffff", weight=400, anchor=None, family="Inter,Segoe UI,Arial,sans-serif", spacing=None):
    attrs = [f'x="{x}"', f'y="{y}"', f'font-size="{size}"', f'fill="{color}"', f'font-weight="{weight}"', f'font-family="{family}"']
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{spacing}"')
    return '<text ' + ' '.join(attrs) + '>' + escape(str(s)) + '</text>'


def r(x, y, w, h, fill, radius=12, stroke=None, extra=""):
    border = f' stroke="{stroke}" stroke-width="1"' if stroke else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"{border} {extra}/>'


def format_count(value):
    return f"{int(value):,}"


def language_rows(data: dict, limit=3):
    sorted_langs = sorted(((k, max(int(v), 0)) for k, v in data.items()), key=lambda p: (-p[1], p[0]))
    total = sum(v for _, v in sorted_langs)
    if total == 0:
        return []
    major = sorted_langs[:limit]
    others = sum(v for _, v in sorted_langs[limit:])
    if others:
        major.append(("Other", others))
    return [(name, 100.0 * size / total) for name, size in major]


def render_svg(data: dict, theme: str, *, demo=False) -> str:
    p = THEMES[theme]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="590" viewBox="0 0 1000 590" role="img" aria-label="GitHub development overview for {escape(data["username"])}">']
    out.append('<defs>')
    out.append(f'<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{p["cyan"]}" stop-opacity="0.65"/><stop offset="45%" stop-color="{p["blue"]}" stop-opacity="0.35"/><stop offset="100%" stop-color="{p["violet"]}" stop-opacity="0.55"/></linearGradient>')
    out.append('</defs>')
    out.append(r(8, 8, 984, 574, p['bg'], 23, 'url(#edge)'))
    out.append(r(32, 32, 5, 54, p['cyan'], 2))
    out.append(t(52, 50, "ENGINEERING / LIVE METRICS", size=12, color=p['cyan'], weight=700, spacing=2))
    out.append(t(52, 86, "Development overview", size=29, color=p['text'], weight=760))
    out.append(r(792, 47, 150, 34, p['surface'], 17, p['stroke']))
    out.append('<circle cx="812" cy="64" r="4" fill="' + p['cyan'] + '"/>')
    out.append(t(827, 69, "GITHUB DATA", size=12, color=p['muted'], weight=650, spacing=1))
    out.append(f'<path d="M52 111 H948" stroke="{p["stroke"]}" stroke-width="1"/>')

    cards = [
        (52, 'contributions', "CONTRIBUTIONS", "LAST 365 DAYS", 'cyan'),
        (356, 'current_streak', "CURRENT STREAK", "CONSECUTIVE DAYS", 'violet'),
        (660, 'longest_streak', "LONGEST STREAK", "IN LAST 365 DAYS", 'blue'),
    ]
    for x, key, label, sub, color_key in cards:
        out.append(r(x, 137, 288, 126, p['surface'], 14, p['stroke']))
        out.append(r(x + 16, 157, 4, 22, p[color_key], 2))
        out.append(t(x + 30, 174, label, size=13, color=p['muted'], weight=650, spacing=0.8))
        out.append(t(x + 22, 229, format_count(data[key]), size=44, color=p[color_key], weight=760))
        out.append(t(x + 224, 245, sub, size=10, color=p['faint'], anchor='end', weight=600))

    # Unified lower row, separate modules in same design system.
    lx, rx, y, h = 52, 510, 286, 248
    out.append(r(lx, y, 438, h, p['panel'], 16, p['stroke']))
    out.append(r(rx, y, 438, h, p['panel'], 16, p['stroke']))
    out.append(t(lx + 22, y + 36, "Development activity", size=19, color=p['text'], weight=740))
    out.append(t(rx + 22, y + 36, "Code distribution", size=19, color=p['text'], weight=740))
    out.append(t(lx + 22, y + 60, "PUBLIC CONTRIBUTIONS · 365 DAYS", size=10, color=p['faint'], weight=650, spacing=0.9))
    out.append(t(rx + 22, y + 60, "OWNED PUBLIC REPOS · CODE BYTES", size=10, color=p['faint'], weight=650, spacing=0.9))

    # Main activity value + two side values.
    out.append(t(lx + 24, y + 135, format_count(data['commits']), size=45, color=p['cyan'], weight=740))
    out.append(t(lx + 24, y + 158, "Commits", size=13, color=p['muted']))
    out.append(f'<path d="M{lx+190} {y+82} V{y+170}" stroke="{p["stroke"]}"/>')
    out.append(t(lx + 218, y + 122, format_count(data['pull_requests']), size=29, color=p['violet'], weight=700))
    out.append(t(lx + 218, y + 144, "Pull requests", size=12, color=p['muted']))
    out.append(t(lx + 344, y + 122, format_count(data['issues']), size=29, color=p['blue'], weight=700))
    out.append(t(lx + 344, y + 144, "Issues", size=12, color=p['muted']))
    out.append(f'<path d="M{lx+22} {y+185} H{lx+416}" stroke="{p["stroke"]}"/>')
    out.append(t(lx + 24, y + 216, f"★ {format_count(data['stars'])} stars earned", size=13, color=p['muted'], weight=570))
    out.append(t(lx + 244, y + 216, f"{format_count(data['reviews'])} PR reviews", size=13, color=p['muted'], weight=570))

    rows = language_rows(data['languages'])
    if not rows:
        out.append(t(rx + 25, y + 136, "No public language data yet", size=15, color=p['muted']))
    else:
        for i, (name, pct) in enumerate(rows):
            color = p[COLORS[min(i, 3)]]
            ry = y + 95 + i * 36
            out.append(t(rx + 24, ry, name[:19], size=14, color=p['text'], weight=590))
            out.append(t(rx + 414, ry, f"{pct:.1f}%", size=13, color=p['muted'], weight=600, anchor="end"))
            out.append(r(rx + 24, ry + 10, 390, 6, p['track'], 3))
            if pct > 0:
                out.append(r(rx + 24, ry + 10, round(390 * pct / 100, 2), 6, color, 3))

    out.append(t(52, 566, "SOURCE: GITHUB GRAPHQL + PUBLIC REPOSITORY LANGUAGE DATA", size=10, color=p['faint'], weight=600, spacing=0.5))
    out.append(t(948, 566, "UPDATED " + data['as_of'], size=10, color=p['muted'], weight=600, anchor="end"))
    if demo:
        out.append(r(812, 118, 136, 20, p['violet'], 5))
        out.append(t(880, 132, "PREVIEW DATA", size=10, color=p['bg'], weight=700, anchor='middle'))
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="hieund1775")
    parser.add_argument("--output-dir", type=Path, default=Path("assets/generated"))
    parser.add_argument("--demo", action="store_true", help="Use explicitly labelled sample data for design tests only")
    args = parser.parse_args()

    if args.demo:
        payload = {
            "username": args.username, "as_of": "2026-11-05", "contributions": 722,
            "current_streak": 10, "longest_streak": 24, "commits": 578,
            "pull_requests": 29, "issues": 0, "reviews": 0, "stars": 1,
            "public_repos": 5, "languages": {"JavaScript": 6024, "TypeScript": 3031, "C#": 722, "Other": 123},
        }
    else:
        payload = collect_live(args.username, os.getenv("GITHUB_TOKEN", ""))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        target = args.output_dir / f"github-telemetry-{theme}.svg"
        target.write_text(render_svg(payload, theme, demo=args.demo), encoding="utf-8")
        print(f"Wrote {target}")
    if not args.demo:
        print("Telemetry updated from GitHub API:", json.dumps({k: v for k, v in payload.items() if k != 'languages'}))


if __name__ == "__main__":
    main()
