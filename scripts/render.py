#!/usr/bin/env python3
"""Render the profile's SVG assets (banner, stats, project cards) from live GitHub data.

Run locally with `GITHUB_TOKEN=$(gh auth token) python3 scripts/render.py`.
The refresh workflow runs it daily and commits only when a number changes.
"""

import json
import os
import pathlib
import urllib.request
from xml.sax.saxutils import escape

USER = "maximpri"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

# duet is Declass's earlier name; counting both would double its numbers.
EXCLUDE = {USER, "duet"}

# Ordered by impact (stars, forks, downloads). Width 840 is the full-width hero card.
FEATURED = [
    ("mlxtop", 840, "Flagship · LLM observability",
     "top for local LLMs. See whether memory, paging or the GPU is slowing your model down, "
     "next to live tokens/s, prefill and queue data from 13 runtimes including oMLX, Ollama, "
     "llama.cpp, vLLM and LM Studio."),
    ("mikrotik-adguardhome", 410, "Network · DNS",
     "Installs, upgrades or swaps AdGuard Home and Pi-hole as a MikroTik "
     "container, with backups, rollback and DNS that stays up throughout."),
    ("declass", 410, "Private AI coding",
     "Terminal coding agent: Claude or GPT writes the code, a local model "
     "reads your secrets, customer data and logs. Every request is checked."),
]

LANG_COLORS = {
    "Rust": "#dea584",
    "Python": "#3572A5",
    "Shell": "#89e051",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Ruby": "#701516",
    "RouterOS Script": "#DE3941",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "PowerShell": "#012456",
}

THEMES = {
    "dark": {
        "bg0": "#0d1117", "bg1": "#111a26", "card": "#161b22", "border": "#30363d",
        "text": "#e6edf3", "muted": "#9198a1", "dots": "#30363d",
        "accent": "#58a6ff", "accent2": "#bc8cff", "chip": "#1c2433", "track": "#21262d",
        "shadow": "0",
    },
    "light": {
        "bg0": "#ffffff", "bg1": "#f3f6fa", "card": "#f6f8fa", "border": "#d0d7de",
        "text": "#1f2328", "muted": "#59636e", "dots": "#d0d7de",
        "accent": "#0969da", "accent2": "#8250df", "chip": "#eef4fc", "track": "#e4e8ec",
        "shadow": "0.18",
    },
}

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

ICON_STAR = (
    "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 "
    "4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 "
    "6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 "
    "0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 "
    ".698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z"
)
ICON_FORK = (
    "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 "
    "2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 "
    "6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 "
    "1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"
)
ICON_TAG = (
    "M1 7.775V2.75C1 1.784 1.784 1 2.75 1h5.025c.464 0 .91.184 1.238.513l6.25 6.25a1.75 1.75 0 0 1 0 "
    "2.474l-5.026 5.026a1.75 1.75 0 0 1-2.474 0l-6.25-6.25A1.752 1.752 0 0 1 1 7.775Zm1.5 0c0 "
    ".066.026.13.073.177l6.25 6.25a.25.25 0 0 0 .354 0l5.025-5.025a.25.25 0 0 0 "
    "0-.354l-6.25-6.25a.25.25 0 0 0-.177-.073H2.75a.25.25 0 0 0-.25.25ZM6 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
)


def api(path):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER + "-profile"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def text_width(s, size):
    """Rough rendered width of sans-serif text, good enough for wrapping and layout."""
    w = 0.0
    for ch in s:
        if ch in "il.,:;'|!·":
            w += 0.27
        elif ch in "fjrt()[]/- ":
            w += 0.34
        elif ch in "mwMW":
            w += 0.84
        elif ch.isupper() or ch.isdigit():
            w += 0.63
        else:
            w += 0.54
    return w * size


def wrap(text, size, max_width, max_lines):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if text_width(trial, size) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        raise SystemExit("blurb too long for card: " + text)
    return lines


def svg(width, height, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">\n'
        f"<title>{escape(title)}</title>\n{body}\n</svg>\n"
    )


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


# ---------------------------------------------------------------- banner

T = 10  # seconds per terminal animation loop


def appear(at):
    """Opacity animation that shows an element `at` seconds into each loop."""
    k = at / T
    return (
        f'<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;{k:.3f};{k + 0.02:.3f};1" '
        f'dur="{T}s" repeatCount="indefinite"/>'
    )


def typed(clip_id, x, y, width, start, end):
    """A clip rectangle that wipes open like typing between `start` and `end` seconds."""
    a, b = start / T, end / T
    return (
        f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{width}" height="22">'
        f'<animate attributeName="width" values="0;0;{width};{width}" keyTimes="0;{a:.3f};{b:.3f};1" '
        f'dur="{T}s" repeatCount="indefinite"/></rect></clipPath>'
    )


def banner(t):
    chips, x = [], 56
    for label in ("Rust", "Local LLMs", "AI privacy", "RouterOS"):
        w = len(label) * 7.4 + 24
        chips.append(
            f'<rect x="{x}" y="242" width="{w:.0f}" height="26" rx="13" fill="{t["chip"]}" stroke="{t["border"]}"/>'
            f'<text x="{x + w / 2:.1f}" y="259.5" class="mono chip" text-anchor="middle">{label}</text>'
        )
        x += w + 10

    tx, ty = 596, 46  # terminal origin
    lx = tx + 18
    body = f"""<defs>
  <style>
    .sans {{ font-family: {SANS}; }}
    .mono {{ font-family: {MONO}; }}
    .name {{ font-size: 52px; font-weight: 700; fill: {t["text"]}; letter-spacing: -1px; }}
    .tag {{ font-size: 19px; fill: {t["muted"]}; }}
    .kicker {{ font-size: 14px; fill: {t["accent"]}; }}
    .chip {{ font-size: 12px; fill: {t["text"]}; }}
    .term {{ font-size: 13px; fill: #e6edf3; }}
    .dim {{ fill: #8b949e; }}
    .ok {{ fill: #3fb950; }}
  </style>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{t["bg0"]}"/><stop offset="1" stop-color="{t["bg1"]}"/>
  </linearGradient>
  <radialGradient id="glowA"><stop offset="0" stop-color="{t["accent"]}" stop-opacity=".22"/><stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></radialGradient>
  <radialGradient id="glowB"><stop offset="0" stop-color="{t["accent2"]}" stop-opacity=".18"/><stop offset="1" stop-color="{t["accent2"]}" stop-opacity="0"/></radialGradient>
  <linearGradient id="ink" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent2"]}"/>
  </linearGradient>
  <linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#3fb950"/><stop offset="1" stop-color="#58a6ff"/>
  </linearGradient>
  <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{t["dots"]}"/></pattern>
  <radialGradient id="fade" cx=".75" cy=".5" r=".75"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>
  <mask id="dotmask"><rect width="1000" height="300" fill="url(#fade)"/></mask>
  <clipPath id="frame"><rect x=".5" y=".5" width="999" height="299" rx="16"/></clipPath>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#0b1220" flood-opacity="{t["shadow"]}"/></filter>
  {typed("c1", lx, ty + 44, 272, 0.4, 1.9)}
  {typed("c2", lx, ty + 68, 70, 2.4, 2.8)}
</defs>
<g clip-path="url(#frame)">
  <rect width="1000" height="300" fill="url(#bg)"/>
  <rect width="1000" height="300" fill="url(#dots)" mask="url(#dotmask)" opacity=".7"/>
  <circle cx="150" cy="30" r="300" fill="url(#glowA)"/>
  <circle cx="900" cy="300" r="280" fill="url(#glowB)"/>
</g>
<rect x=".5" y=".5" width="999" height="299" rx="16" fill="none" stroke="{t["border"]}"/>

<text x="56" y="96" class="mono kicker">$ whoami</text>
<text x="54" y="152" class="sans name">Maxim Priezjev</text>
<rect x="56" y="166" width="64" height="3" rx="1.5" fill="url(#ink)"/>
<text x="56" y="198" class="sans tag">Tools for running AI on your own hardware,</text>
<text x="56" y="224" class="sans tag">and for keeping your private data on it.</text>
{"".join(chips)}

<g filter="url(#shadow)">
  <rect x="{tx}" y="{ty}" width="360" height="208" rx="12" fill="#0b0f14" stroke="#30363d"/>
</g>
<circle cx="{tx + 20}" cy="{ty + 16}" r="5.5" fill="#ff5f57"/>
<circle cx="{tx + 38}" cy="{ty + 16}" r="5.5" fill="#febc2e"/>
<circle cx="{tx + 56}" cy="{ty + 16}" r="5.5" fill="#28c840"/>
<text x="{tx + 196}" y="{ty + 20}" class="mono dim" font-size="11.5" text-anchor="middle">zsh — ~/projects</text>
<line x1="{tx}" y1="{ty + 32.5}" x2="{tx + 360}" y2="{ty + 32.5}" stroke="#21262d"/>

<g>
  <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.93;0.97;1" dur="{T}s" repeatCount="indefinite"/>
  <text x="{lx}" y="{ty + 60}" class="mono term" clip-path="url(#c1)"><tspan class="ok">$</tspan> brew install maximpri/tap/mlxtop</text>
  <text x="{lx}" y="{ty + 84}" class="mono term" clip-path="url(#c2)"><tspan class="ok">$</tspan> mlxtop</text>
  <g>{appear(3.2)}
    <text x="{lx}" y="{ty + 108}" class="mono term dim">Memory</text>
    <rect x="{lx + 66}" y="{ty + 99}" width="160" height="10" rx="3" fill="#21262d"/>
    <rect x="{lx + 66}" y="{ty + 99}" width="104" height="10" rx="3" fill="url(#bar)">
      <animate attributeName="width" values="0;0;104;104" keyTimes="0;0.32;0.42;1" calcMode="spline" keySplines="0 0 1 1;.2 .8 .2 1;0 0 1 1" dur="{T}s" repeatCount="indefinite"/>
    </rect>
    <text x="{lx + 238}" y="{ty + 108}" class="mono term">41.6/64 GB</text>
  </g>
  <g>{appear(3.7)}
    <text x="{lx}" y="{ty + 132}" class="mono term dim">Gen</text>
    <text x="{lx + 66}" y="{ty + 132}" class="mono term">38.6 tok/s <tspan class="dim">· prefill 1.4k/s</tspan></text>
  </g>
  <g>{appear(4.3)}
    <text x="{lx}" y="{ty + 156}" class="mono term ok">✓ Healthy</text>
  </g>
  <g>{appear(4.9)}
    <text x="{lx}" y="{ty + 180}" class="mono term"><tspan class="ok">$</tspan></text>
    <rect x="{lx + 16}" y="{ty + 169}" width="8" height="15" fill="#e6edf3">
      <animate attributeName="opacity" values="1;0" dur="1.1s" calcMode="discrete" repeatCount="indefinite"/>
    </rect>
  </g>
</g>"""
    return svg(1000, 300, body, "Maxim Priezjev: tools for running AI on your own hardware, and for keeping your private data on it.")


# ---------------------------------------------------------------- cards

def card(t, repo, w, kicker, blurb, release):
    h, pad = (200 if w > 600 else 184), 22
    lang = repo.get("language") or ""
    lines = wrap(blurb, 13, w - 2 * pad, 3)
    desc = "".join(
        f'<text x="{pad}" y="{88 + i * 19}" class="sans desc">{escape(line)}</text>' for i, line in enumerate(lines)
    )

    # Wide cards have room under a short blurb for the repo's topics.
    chips, cx = [], pad
    if w > 600 and len(lines) < 3:
        cy = 88 + len(lines) * 19 - 4
        for topic in repo.get("topics", [])[:8]:
            tw = text_width(topic, 11.5) + 20
            chips.append(
                f'<rect x="{cx:.1f}" y="{cy}" width="{tw:.1f}" height="21" rx="10.5" fill="{t["chip"]}"/>'
                f'<text x="{cx + tw / 2:.1f}" y="{cy + 14.5}" class="sans topic" text-anchor="middle">{escape(topic)}</text>'
            )
            cx += tw + 6

    pill = ""
    if release:
        pw = text_width(release, 11.5) + 34
        px = w - pad - pw
        pill = (
            f'<rect x="{px:.1f}" y="18" width="{pw:.1f}" height="22" rx="11" fill="{t["chip"]}" stroke="{t["border"]}"/>'
            f'<path d="{ICON_TAG}" transform="translate({px + 9:.1f} 23.5) scale(.69)" fill="{t["accent"]}"/>'
            f'<text x="{px + 24:.1f}" y="33" class="mono pill">{escape(release)}</text>'
        )

    fy = h - 24  # footer baseline
    x = pad
    footer = []
    if lang:
        footer.append(f'<circle cx="{x + 5}" cy="{fy - 4}" r="5.5" fill="{LANG_COLORS.get(lang, "#8b949e")}"/>')
        footer.append(f'<text x="{x + 16}" y="{fy}" class="sans meta">{escape(lang)}</text>')
        x += 16 + text_width(lang, 12) + 18
    for icon, n in ((ICON_STAR, repo["stargazers_count"]), (ICON_FORK, repo["forks_count"])):
        footer.append(f'<path d="{icon}" transform="translate({x:.1f} {fy - 11.5}) scale(.8)" fill="{t["muted"]}"/>')
        footer.append(f'<text x="{x + 18:.1f}" y="{fy}" class="sans meta">{fmt(n)}</text>')
        x += 18 + text_width(fmt(n), 12) + 18
    spdx = (repo.get("license") or {}).get("spdx_id")
    if spdx and spdx != "NOASSERTION":
        footer.append(f'<text x="{w - pad}" y="{fy}" class="sans meta" text-anchor="end">{escape(spdx)}</text>')

    body = f"""<defs>
  <style>
    .sans {{ font-family: {SANS}; }}
    .mono {{ font-family: {MONO}; }}
    .kicker {{ font-size: 10.5px; font-weight: 600; letter-spacing: 1.3px; fill: {t["accent"]}; }}
    .name {{ font-size: 19px; font-weight: 700; fill: {t["text"]}; }}
    .desc {{ font-size: 13px; fill: {t["muted"]}; }}
    .meta {{ font-size: 12px; fill: {t["muted"]}; }}
    .pill {{ font-size: 11.5px; fill: {t["text"]}; }}
    .topic {{ font-size: 11.5px; font-weight: 500; fill: {t["accent"]}; }}
  </style>
  <linearGradient id="ink" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent2"]}"/>
  </linearGradient>
  <clipPath id="frame"><rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12"/></clipPath>
</defs>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{t["card"]}" stroke="{t["border"]}"/>
<rect width="{w}" height="3" fill="url(#ink)" clip-path="url(#frame)"/>
<text x="{pad}" y="34" class="sans kicker">{escape(kicker.upper())}</text>
<text x="{pad}" y="62" class="sans name">{escape(repo["name"])}</text>
{pill}
{desc}
{"".join(chips)}
<line x1="{pad}" y1="{fy - 24.5}" x2="{w - pad}" y2="{fy - 24.5}" stroke="{t["border"]}" stroke-dasharray="2 4"/>
{"".join(footer)}"""
    return svg(w, h, body, f"{repo['name']}: {blurb}")


# ---------------------------------------------------------------- stats

def stats(t, metrics, languages):
    w, h = 840, 172
    total = sum(languages.values()) or 1
    ranked = sorted(languages.items(), key=lambda kv: -kv[1])
    shown = ranked[:5]
    other = total - sum(v for _, v in shown)

    cols = []
    cw = (w - 40) / len(metrics)
    for i, (label, value) in enumerate(metrics):
        cx = 20 + cw * i + cw / 2
        cols.append(
            f'<text x="{cx:.1f}" y="62" class="sans value" text-anchor="middle">{escape(value)}</text>'
            f'<text x="{cx:.1f}" y="86" class="sans label" text-anchor="middle">{escape(label.upper())}</text>'
        )
        if i:
            cols.append(f'<line x1="{20 + cw * i:.1f}" y1="34" x2="{20 + cw * i:.1f}" y2="92" stroke="{t["border"]}"/>')

    bar, legend, x, lx = [], [], 28.0, 28.0
    span = w - 56
    for name, size in shown + ([("Other", other)] if other else []):
        frac = size / total
        color = LANG_COLORS.get(name, "#8b949e")
        bar.append(f'<rect x="{x:.2f}" y="112" width="{span * frac:.2f}" height="8" fill="{color}"/>')
        x += span * frac
        label = f"{name} {frac * 100:.1f}%"
        legend.append(
            f'<circle cx="{lx + 4}" cy="146" r="4.5" fill="{color}"/>'
            f'<text x="{lx + 14}" y="150" class="sans legend">{escape(label)}</text>'
        )
        lx += 14 + text_width(label, 12) + 22

    body = f"""<defs>
  <style>
    .sans {{ font-family: {SANS}; }}
    .value {{ font-size: 32px; font-weight: 700; fill: url(#ink); }}
    .label {{ font-size: 11px; font-weight: 600; letter-spacing: 1.2px; fill: {t["muted"]}; }}
    .legend {{ font-size: 12px; fill: {t["muted"]}; }}
  </style>
  <linearGradient id="ink" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent2"]}"/>
  </linearGradient>
  <clipPath id="barclip"><rect x="28" y="112" width="{span}" height="8" rx="4"/></clipPath>
</defs>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{t["card"]}" stroke="{t["border"]}"/>
{"".join(cols)}
<rect x="28" y="112" width="{span}" height="8" rx="4" fill="{t["track"]}"/>
<g clip-path="url(#barclip)">{"".join(bar)}</g>
{"".join(legend)}"""
    summary = ", ".join(f"{label} {value}" for label, value in metrics)
    return svg(w, h, body, f"GitHub stats: {summary}")


# ---------------------------------------------------------------- main

def main():
    repos = [
        r for r in api(f"/users/{USER}/repos?type=owner&per_page=100")
        if not r["fork"] and not r["private"] and r["name"] not in EXCLUDE
    ]
    by_name = {r["name"]: r for r in repos}

    languages, releases, latest = {}, 0, {}
    for r in repos:
        for lang, size in api(f"/repos/{USER}/{r['name']}/languages").items():
            languages[lang] = languages.get(lang, 0) + size
        published = [rel for rel in api(f"/repos/{USER}/{r['name']}/releases?per_page=100") if not rel["draft"]]
        releases += len(published)
        if published:
            latest[r["name"]] = published[0]["tag_name"]

    metrics = [
        ("Stars", fmt(sum(r["stargazers_count"] for r in repos))),
        ("Forks", fmt(sum(r["forks_count"] for r in repos))),
        ("Releases", fmt(releases)),
        ("Projects", fmt(len(repos))),
    ]

    OUT.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        (OUT / f"banner-{theme}.svg").write_text(banner(t))
        (OUT / f"stats-{theme}.svg").write_text(stats(t, metrics, languages))
        for name, width, kicker, blurb in FEATURED:
            (OUT / f"card-{name}-{theme}.svg").write_text(card(t, by_name[name], width, kicker, blurb, latest.get(name)))
    print("rendered:", ", ".join(f"{k} {v}" for k, v in metrics))


if __name__ == "__main__":
    main()
