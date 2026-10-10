"""Syntetyczne odpowiedzi strony glownej KSI do testow motywow okazjonalnych.

Celowo zmyslone: identyfikatory, kolory, nazwy plikow i grafiki nie pochodza
z ksi.sh - repozytorium jest publiczne, a motywy i terminy sa tajne (konkurs
odznak). Ksztalt (atrybuty <html>, blok :root, modul wejsciowy Vite) odpowiada
temu, co strona wysyla.
"""

from __future__ import annotations

OCCASION = "sample-occasion"
COLOR = "#0b1a2a"
MODULE_PATH = "/assets/Entry123.js"
FACADE_PATH = "/assets/Facade123.svg"
FACADE_PL_PATH = "/assets/FacadePl1.svg"
FACADE_EN_PATH = "/assets/FacadeEn1.svg"

PALETTE_BLOCK = (
    ":root { --color-night-950: #0b1a2a; --color-night-900: #11243a; --color-night-800: #173049; "
    "--color-night-700: #21405e; --color-night-600: #2d5275; --color-night-400: #7f9ab5; "
    "--color-night-300: #a9bdd1; --color-night-200: #cfdbe7; --color-night-100: #e6eef6; "
    "--color-accent: #1d5c3a; --color-accent-hover: #24704a; --color-accent-light: #7fd6a4; }"
)

# Krytyczny CSS strony (beasties) tez ma :root z kolorami - nie jest paleta okazji.
CRITICAL_CSS = (
    "@layer theme{:root{--color-night-950:#15151f;--color-accent:#5c5f8a;--font-sans:Inter}}"
    "body{margin:0}"
)

ENTRY_SCRIPT = (
    '<script type="module">let s=!1;const n=()=>{for(const e of["/assets/App1.js"]){}'
    f'import("{MODULE_PATH}")}};addEventListener("keydown",n,{{once:!0}});</script>'
)


def landing_html(
    *,
    occasion: str | None = OCCASION,
    color: str | None = COLOR,
    palette: str | None = PALETTE_BLOCK,
    entry_script: str | None = ENTRY_SCRIPT,
) -> str:
    """Strona glowna w ksztalcie ksi.sh; None pomija dany element."""
    attrs = ['lang="pl"']
    if occasion is not None:
        attrs.append(f'data-occasion="{occasion}"')
    if color is not None:
        attrs.append(f'data-color="{color}"')
    attrs.append("data-beasties-container")
    head = [f"<style>{CRITICAL_CSS}</style>"]
    if palette is not None:
        head.append(f"<style>{palette}</style>")
    body = ["<div id=root><h1>Strona</h1></div>"]
    if entry_script is not None:
        body.append(entry_script)
    return (
        f"<!doctype html><html {' '.join(attrs)}><head><meta charset=UTF-8>{''.join(head)}</head>"
        f"<body>{''.join(body)}</body></html>"
    )


def entry_module(*, occasion: str = OCCASION, facade: str = "a") -> str:
    """Zminifikowany modul wejsciowy okazji; `facade` to wyrazenie po `facade:`."""
    return (
        'const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/Deco1.js"])))=>i.map(i=>d[i]);'
        'import{s as e,_ as o}from"./App1.js";'
        f'const a="{FACADE_PATH}",p="{FACADE_PL_PATH}",q="{FACADE_EN_PATH}";'
        f'e({{occasion:"{occasion}",'
        f"facade:{facade}}});"
    )


SVG_NS = 'xmlns="http://www.w3.org/2000/svg"'

# Fasada przelaczajaca kolory wg trybu, z animacja - jak grafiki ksi.sh.
FACADE_SVG = (
    f'<svg role="img" aria-hidden="true" {SVG_NS} viewBox="0 0 100 50">'
    "<style>.facade{fill:#2b2d42}@media (prefers-color-scheme:dark){.facade{fill:#2f3143}}"
    ".blink{animation:blink 2s infinite}@keyframes blink{50%{opacity:.4}}"
    "@media (prefers-reduced-motion:reduce){.blink{animation:none}}</style>"
    '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient>'
    '<path id="arc" d="M0 0 L10 10"/></defs>'
    '<path class="facade" d="M0 0h100v50H0z"/>'
    '<rect class="blink" x="1" y="1" width="5" height="5" fill="url(#g)"/>'
    '<text><textPath href="#arc">KSI</textPath></text>'
    '<use href="#arc"/><animate attributeName="opacity" values="1;0;1" dur="3s"/>'
    "</svg>"
)
