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
        "panel": "#191E2E", "secondary": "#141C2D", "stroke": "#303B55",
        "text": "#F2F6FD", "muted": "#BBC9E1", "faint": "#8193AF", "track": "#2D3853",
        "cyan": "#66D9EA", "violet": "#C3A4F7", "blue": "#77A6FA", "other": "#627BA1",
        "divider": "#42506A", "eyebrow": "#8EA9CC", "hero_a": "#1B2031", "hero_b": "#1A1B30",
    },
    "light": {
        "panel": "#FFFFFF", "secondary": "#F6F8FD", "stroke": "#D7DFEF",
        "text": "#16233C", "muted": "#4B5D7B", "faint": "#637897", "track": "#E3EAF4",
        "cyan": "#087D98", "violet": "#7551BD", "blue": "#2D66BA", "other": "#8A9AB0",
        "divider": "#D1DCEB", "eyebrow": "#526989", "hero_a": "#F7F9FE", "hero_b": "#F5F4FC",
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
    """Compact analytics inspired by classic three-column streak cards.

    One wide streak panel sits over two balanced cards. SVG remains self-contained
    (no external fonts, HTML or JS), works in GitHub's image proxy and is rendered
    in dedicated dark/light variants. Values are computed from API data.
    """
    if theme not in THEMES:
        raise ValueError(f"Unsupported theme: {theme}")
    p = THEMES[theme]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="552" '
        f'viewBox="0 0 1000 552" role="img" aria-label="GitHub contribution analytics for {escape(data["username"])}">'
    ]
    out.extend([
        '<defs>',
        '<linearGradient id="hero" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{p["hero_a"]}"/>'
        f'<stop offset="100%" stop-color="{p["hero_b"]}"/>'
        '</linearGradient>',
        '<linearGradient id="streakRing" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{p["blue"]}"/>'
        f'<stop offset="100%" stop-color="{p["violet"]}"/>'
        '</linearGradient>',
        '</defs>',
    ])
    # Deliberately transparent outer canvas so each block breathes on GitHub.
    # Top: classic 3-column streak card, balanced against the two cards below.
    out.append(r(125, 12, 750, 224, 'url(#hero)', 17, p['stroke']))
    out.append(t(154, 46, 'GITHUB  /  CONTRIBUTION STREAK', size=14, color=p['eyebrow'], weight=700, spacing=1.25))
    out.append(t(846, 46, 'LAST 365 DAYS', size=12, color=p['faint'], weight=600, anchor='end', spacing=0.8))
    out.append(f'<path d="M373 74 V206 M626 74 V206" stroke="{p["divider"]}" stroke-width="1"/>')

    out.append(t(248, 126, format_count(data['contributions']), size=48, color=p['blue'], weight=780, anchor='middle'))
    out.append(t(248, 163, 'Total contributions', size=18, color=p['text'], anchor='middle', weight=650))
    out.append(t(248, 194, 'GitHub activity', size=13, color=p['muted'], anchor='middle'))

    # The center ring is intentionally the focal point, as in the reference.
    out.append(f'<circle cx="500" cy="129" r="50" fill="none" stroke="{p["track"]}" stroke-width="7"/>')
    out.append(f'<circle cx="500" cy="129" r="50" fill="none" stroke="url(#streakRing)" '
               'stroke-width="7" stroke-linecap="round" stroke-dasharray="276 38" transform="rotate(-90 500 129)"/>')
    out.append(t(500, 145, format_count(data['current_streak']), size=45, color=p['violet'], weight=780, anchor='middle'))
    out.append(f'<path d="M499 71 C488 62,492 54,496 49 C497 57,501 58,504 53 '
               'C516 64,510 76,502 79 C495 80,491 75,493 68 Z" '
               f'fill="{p["violet"]}" stroke="{p["hero_a"]}" stroke-width="3"/>')
    out.append(t(500, 204, 'Current streak', size=18, color=p['text'], anchor='middle', weight=690))

    out.append(t(750, 126, format_count(data['longest_streak']), size=48, color=p['blue'], weight=780, anchor='middle'))
    out.append(t(750, 163, 'Longest streak', size=18, color=p['text'], anchor='middle', weight=650))
    out.append(t(750, 194, 'In the last 365 days', size=13, color=p['muted'], anchor='middle'))

    # Bottom left: intentionally removes the opaque 'C+' grade.
    lx, ly, lw, lh = 23, 266, 465, 272
    rx = 512
    out.append(r(lx, ly, lw, lh, p['panel'], 16, p['stroke']))
    out.append(r(rx, ly, lw, lh, p['panel'], 16, p['stroke']))
    out.append(r(lx + 22, ly + 22, 4, 31, p['cyan'], 2))
    out.append(t(lx + 39, ly + 44, 'GitHub activity', size=22, color=p['text'], weight=740))
    out.append(t(lx + 25, ly + 75, 'CONTRIBUTION EVENTS  ·  LAST 365 DAYS', size=12, color=p['faint'], weight=590, spacing=0.35))

    out.append(t(lx + 30, ly + 152, format_count(data['commits']), size=49, color=p['cyan'], weight=770))
    out.append(t(lx + 31, ly + 177, 'Commits', size=16, color=p['muted']))
    out.append(f'<path d="M{lx+218} {ly+101} V{ly+187}" stroke="{p["divider"]}"/>')
    out.append(t(lx + 241, ly + 143, format_count(data['pull_requests']), size=32, color=p['violet'], weight=750))
    out.append(t(lx + 241, ly + 170, 'Pull requests', size=14, color=p['muted']))
    out.append(t(lx + 365, ly + 143, format_count(data['issues']), size=32, color=p['blue'], weight=750))
    out.append(t(lx + 365, ly + 170, 'Issues', size=14, color=p['muted']))
    out.append(f'<path d="M{lx+25} {ly+206} H{lx+440}" stroke="{p["divider"]}"/>')
    out.append(t(lx + 30, ly + 239, f"★ {format_count(data['stars'])} stars", size=15, color=p['muted'], weight=600))
    out.append(t(lx + 260, ly + 239, f"{format_count(data['reviews'])} code reviews", size=15, color=p['muted'], weight=600))

    # Bottom right: a single comparison bar plus 2x2 legend, rather than
    # tiny dense percent rows. 'Other' is merged, not falsely labelled skill.
    out.append(r(rx + 22, ly + 22, 4, 31, p['violet'], 2))
    out.append(t(rx + 39, ly + 44, 'Languages by code', size=22, color=p['text'], weight=740))
    out.append(t(rx + 25, ly + 75, 'OWNED PUBLIC REPOS  ·  CODE BYTES', size=12, color=p['faint'], weight=590, spacing=0.35))

    rows = language_rows(data['languages'])
    if not rows:
        out.append(t(rx + 27, ly + 151, 'No public language data yet', size=17, color=p['muted']))
    else:
        bar_x, bar_y, bar_w, bar_h = rx + 27, ly + 110, 409, 14
        out.append(r(bar_x, bar_y, bar_w, bar_h, p['track'], 7))
        accum = 0.0
        for i, (name, pct) in enumerate(rows):
            width = min(bar_w - accum, max(0.0, bar_w * pct / 100.0))
            if width > 0.05:
                out.append(r(round(bar_x + accum, 2), bar_y, round(width, 2), bar_h,
                             p[COLORS[min(i, 3)]], 1))
            accum += width
        # Each item has a generous hit-area for readability after GitHub scales.
        for i, (name, pct) in enumerate(rows[:4]):
            col, row = i % 2, i // 2
            x = rx + 28 + col * 210
            y = ly + 160 + row * 48
            color = p[COLORS[min(i, 3)]]
            out.append(f'<circle cx="{x+7}" cy="{y-5}" r="6" fill="{color}"/>')
            # Enforce short labels: language names originate from GitHub API.
            out.append(t(x + 21, y, name[:16], size=15, color=p['text'], weight=600))
            out.append(t(x + 181, y, f"{pct:.1f}%", size=14, color=p['muted'],
                         weight=600, anchor='end'))

    if demo:
        out.append(t(846, 222, 'DESIGN PREVIEW · DEMO', size=11, color=p['faint'],
                     weight=700, anchor='end'))
    else:
        out.append(t(846, 222, 'UPDATED ' + data['as_of'], size=11,
                     color=p['faint'], weight=650, anchor='end'))
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
            "username": args.username, "as_of": "2026-11-06", "contributions": 723,
            "current_streak": 10, "longest_streak": 24, "commits": 579,
            "pull_requests": 29, "issues": 0, "reviews": 0, "stars": 1,
            "public_repos": 5, "languages": {"JavaScript": 5970, "TypeScript": 3000, "C#": 710, "Other": 310},
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
