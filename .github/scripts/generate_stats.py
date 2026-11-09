"""Generate profile cards from public GitHub data using the standard library."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def api(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-profile-cards",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com{path}", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        # Do not print request headers or credentials in workflow logs.
        raise RuntimeError(f"GitHub API returned HTTP {error.code} for {path}") from None


def collect(username):
    profile = api(f"/users/{username}")
    repositories = []
    page = 1
    while True:
        batch = api(f"/users/{username}/repos?" + urlencode({
            "type": "owner", "per_page": 100, "page": page,
        }))
        repositories.extend(repo for repo in batch if not repo["fork"])
        if len(batch) < 100:
            break
        page += 1
    languages = Counter()
    for repo in repositories:
        # Count GitHub Linguist byte totals across public, non-fork repositories.
        languages.update(api(f"/repos/{repo['full_name']}/languages"))
    stats = [
        ("Public repositories (excluding forks)", len(repositories)),
        ("Stars earned", sum(repo["stargazers_count"] for repo in repositories)),
        ("Forks received", sum(repo["forks_count"] for repo in repositories)),
        ("Followers", profile["followers"]),
        ("Following", profile["following"]),
    ]
    return stats, languages


def text(x, y, content, color, size=13, extra=""):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'{extra}>{escape(str(content))}</text>')


def card(title, description, body, dark, updated):
    background, foreground, border, accent = (
        ("#1a1b27", "#a9b1d6", "#30354a", "#70a5fd") if dark else
        ("#ffffff", "#434d58", "#d1d9e0", "#0969da")
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="235" '
        'viewBox="0 0 495 235" role="img" aria-labelledby="title description">'
        f'<title id="title">{escape(title)}</title>'
        f'<desc id="description">{escape(description)}</desc>'
        f'<rect x="0.5" y="0.5" width="494" height="234" rx="8" '
        f'fill="{background}" stroke="{border}"/>'
        '<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">'
        + text(22, 32, title, accent, 18, 'font-weight="600"')
        + body(foreground, accent)
        + text(22, 218, f"Public data · Updated {updated} UTC", foreground, 10)
        + '</g></svg>\n'
    )


def render(username, stats, languages, output):
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output.mkdir(parents=True, exist_ok=True)
    for dark in (False, True):
        suffix = "-dark" if dark else ""

        def stats_body(foreground, accent):
            return "".join(
                text(22, 65 + index * 28, label, foreground)
                + text(470, 65 + index * 28, f"{value:,}", accent, 14,
                       'text-anchor="end" font-weight="600"')
                for index, (label, value) in enumerate(stats)
            )

        (output / f"github-stats{suffix}.svg").write_text(card(
            f"{username} · GitHub Stats",
            "; ".join(f"{label}: {value}" for label, value in stats),
            stats_body, dark, updated,
        ), encoding="utf-8")

        total = sum(languages.values())
        top = languages.most_common(8)

        def languages_body(foreground, accent):
            if not total:
                return text(22, 80, "No public language data yet", foreground)
            rows = text(22, 54, "By code bytes · public repositories · excluding forks", foreground, 10)
            for index, (name, count) in enumerate(top):
                y = 75 + index * 17
                share = count / total
                rows += text(22, y, name, foreground, 12)
                rows += (f'<rect x="170" y="{y - 9}" width="{230 * share:.2f}" '
                         f'height="8" rx="4" fill="{accent}"/>')
                rows += text(470, y, f"{share:.1%}", foreground, 12, 'text-anchor="end"')
            return rows

        (output / f"top-langs{suffix}.svg").write_text(card(
            "Most Used Languages",
            "Language shares by code bytes across public, non-fork repositories; "
            + "; ".join(f"{name}: {count / total:.1%}" for name, count in top),
            languages_body, dark, updated,
        ), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.username):
        parser.error("Invalid GitHub username")
    stats, languages = collect(args.username)
    render(args.username, stats, languages, args.output)
    print(f"Generated four profile cards for {args.username}")


if __name__ == "__main__":
    main()
