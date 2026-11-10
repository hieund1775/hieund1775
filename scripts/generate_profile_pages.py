#!/usr/bin/env python3
"""Publish GitHub profile images to a Pages artifact, never to a Git commit.

Every hourly run rebuilds weather and reuses the published telemetry and GIF.
One run daily refreshes all three products from their respective data sources.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DRAGON_SITE = ROOT / 'dragon-site'
SITE_URL = 'https://hieund1775.github.io/hieund1775'
WEATHER_URL = (
    'https://api.open-meteo.com/v1/forecast'
    '?latitude=10.8231&longitude=106.6297'
    '&current=temperature_2m,weather_code'
    '&timezone=Asia%2FHo_Chi_Minh'
)
ASSETS = {
    'github-telemetry-dark.svg': ROOT / 'assets/generated/github-telemetry-dark.svg',
    'github-telemetry-light.svg': ROOT / 'assets/generated/github-telemetry-light.svg',
    'game.gif': ROOT / 'game.gif',
}


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={'User-Agent': 'github-profile-pages/1.0', 'Cache-Control': 'no-cache'})
    with urlopen(req, timeout=16) as response:
        if int(getattr(response, 'status', 200)) != 200:
            raise RuntimeError(f'Unexpected status for {url}')
        data = response.read(18 * 1024 * 1024 + 1)
    if len(data) > 18 * 1024 * 1024:
        raise RuntimeError(f'Asset unexpectedly large: {url}')
    return data


def valid_image(name: str, data: bytes) -> bool:
    if name.endswith('.gif'):
        return data[:6] in (b'GIF89a', b'GIF87a') and len(data) > 100
    return b'<svg' in data[:500].lower() and b'</svg>' in data[-1000:].lower()


def fallback_asset(name: str, destination: Path) -> None:
    # Reuse the previously published file without creating any new Git commit.
    # On the first deployment Pages does not yet exist, so use checked-in assets.
    try:
        remote = fetch_bytes(f'{SITE_URL}/{name}')
        if valid_image(name, remote):
            destination.write_bytes(remote)
            print(f'Reused published {name}', flush=True)
            return
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
        print(f'Published {name} not available ({exc}); using repository copy', flush=True)
    source = ASSETS[name]
    data = source.read_bytes()
    if not valid_image(name, data):
        raise RuntimeError(f'Neither published nor local {name} is a valid image')
    destination.write_bytes(data)
    print(f'Used checked-in fallback for {name}', flush=True)


def generate_telemetry(destination: Path) -> None:
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        print('GITHUB_TOKEN missing, preserving last telemetry', flush=True)
        return
    cmd = [sys.executable, 'scripts/generate_telemetry.py', '--username', 'hieund1775']
    try:
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=180, env=os.environ.copy())
        for name in ('github-telemetry-dark.svg', 'github-telemetry-light.svg'):
            data = ASSETS[name].read_bytes()
            if not valid_image(name, data):
                raise RuntimeError(f'Generated {name} is invalid')
            (destination / name).write_bytes(data)
        print('Generated fresh GitHub telemetry', flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Telemetry refresh failed; publishing last known good data: {exc}', flush=True)


def generate_game(destination: Path) -> None:
    if not os.environ.get('GH_TOKEN'):
        print('GH_TOKEN missing, preserving last Space Shooter GIF', flush=True)
        return
    game_path = destination / 'game.gif'
    previous_game = game_path.read_bytes()
    cmd = ['gh-space-shooter', 'hieund1775', '--output', str(game_path), '--strategy', 'random', '--fps', '40']
    try:
        subprocess.run(cmd, cwd=ROOT, check=True, timeout=240, env=os.environ.copy())
        if not valid_image('game.gif', (destination / 'game.gif').read_bytes()):
            raise RuntimeError('Generated Space Shooter GIF was invalid')
        print('Generated fresh Space Shooter GIF', flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Space Shooter refresh failed; publishing last known good data: {exc}', flush=True)
        # Restore the last valid image, even after a partial failed write.
        game_path.write_bytes(previous_game)


def weather_snapshot() -> tuple[str, str]:
    now = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))
    try:
        info = json.loads(fetch_bytes(WEATHER_URL))
        cur = info['current']
        degree = round(float(cur['temperature_2m']))
        code = int(cur['weather_code'])
        if code == 0:
            icon = '☀️'
        elif code in (1, 2):
            icon = '🌤️'
        elif code == 3:
            icon = '☁️'
        elif code in (45, 48):
            icon = '🌫️'
        elif code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67):
            icon = '🌧️'
        elif code in (71, 73, 75, 77, 85, 86):
            icon = '❄️'
        elif code in (80, 81, 82):
            icon = '🌦️'
        elif code in (95, 96, 99):
            icon = '⛈️'
        else:
            icon = '🌤️'
        return f'{icon}  Ho Chi Minh City  ·  {degree}°C', now.strftime('%d/%m/%Y')
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError, TypeError, TimeoutError, OSError) as exc:
        print(f'Weather unavailable: {exc}', flush=True)
        return '🌤  Ho Chi Minh City  ·  Weather temporarily unavailable', now.strftime('%d/%m/%Y')


def make_weather_svg(theme: str, title: str, updated: str) -> bytes:
    # SVG is theme-aware, without a colored panel. Fonts follow the classic README.
    foreground = '#C6D6E5' if theme == 'dark' else '#304351'
    secondary = '#91A6B5' if theme == 'dark' else '#6C7D8B'
    safe_title = html.escape(title)
    safe_updated = html.escape(updated)
    markup = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="48" viewBox="0 0 1000 48" role="img" aria-label="{safe_title}; updated {safe_updated}">
<text x="500" y="21" text-anchor="middle" fill="{foreground}" font-family="Segoe UI,Arial,sans-serif" font-size="17" font-weight="600">{safe_title}</text>
<text x="500" y="40" text-anchor="middle" fill="{secondary}" font-family="Segoe UI,Arial,sans-serif" font-size="11">Updated {safe_updated} · refreshed hourly</text>
</svg>'''
    return markup.encode('utf-8')


def build(mode: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    # Always stage last-known-good assets first, including on a full refresh.
    for name in ASSETS:
        fallback_asset(name, destination / name)
    if mode == 'full':
        generate_telemetry(destination)
        generate_game(destination)
        # If refresh failed, an earlier valid image still exists; verify below.
    title, updated = weather_snapshot()
    for theme in ('dark', 'light'):
        (destination / f'weather-{theme}.svg').write_bytes(make_weather_svg(theme, title, updated))
    (destination / 'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>GitHub profile assets</title><meta name="viewport" content="width=device-width, initial-scale=1"><main style="font:16px system-ui;max-width:700px;margin:48px auto;padding:24px"><h1>GitHub Profile Assets</h1><p>Weather, telemetry and Space Shooter assets, automatically published via GitHub Actions without Git commits.</p><ul><li><a href="weather-dark.svg">Weather</a></li><li><a href="github-telemetry-dark.svg">GitHub telemetry</a></li><li><a href="game.gif">Space Shooter GIF</a></li><li><a href="dragon/">🐉 Interactive Dragon Mode</a></li></ul></main></html>''', encoding='utf-8')
    # Preserve the interactive profile across BOTH hourly weather and full refreshes.
    if not (DRAGON_SITE / 'index.html').is_file():
        raise RuntimeError('Repo Dragon assets missing; will not deploy incomplete Pages site')
    shutil.copytree(DRAGON_SITE, destination / 'dragon', dirs_exist_ok=True)
    (destination / '.nojekyll').touch()
    for name in (*ASSETS.keys(), 'weather-dark.svg', 'weather-light.svg'):
        if not valid_image(name, (destination / name).read_bytes()):
            raise RuntimeError(f'Invalid Pages output: {name}')
        print(f'{name}: {(destination / name).stat().st_size:,} bytes', flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=('full', 'weather'), required=True)
    ap.add_argument('--output', type=Path, default=ROOT / '_site')
    args = ap.parse_args()
    build(args.mode, args.output.resolve())


if __name__ == '__main__':
    main()
