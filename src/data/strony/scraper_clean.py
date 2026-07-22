import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque, Counter
from pathlib import Path
import re


START_URLS = [
    "https://matinf.uj.edu.pl/",
    "https://kmsuj.matinf.uj.edu.pl/",
    "https://nkr.si/",
]

ALLOWED_DOMAINS = {urlparse(u).netloc for u in START_URLS}
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = REPO_ROOT / "data" / "strony" / "webiste_data_scraper_clean.txt"
DELAY = 0.2
MAX_PAGES = 1000

WIKIPEDIA_URLS = [
    "https://pl.wikipedia.org/wiki/Wydzia%C5%82_Matematyki_i_Informatyki_Uniwersytetu_Jagiello%C5%84skiego",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

FALLBACK_USED = []

# ---------------------------------------------------------------------------
# CZYSZCZENIE ŚMIECI
# ---------------------------------------------------------------------------

# Elementy, które trzeba wyciąć PRZED pobraniem tekstu - to są zwykle
# zdublowane wersje responsywne (mobile/desktop), etykiety dla czytników
# ekranu, liczniki i inne czysto-dekoracyjne UI Liferaya.
NOISE_SELECTORS = [
    "[aria-hidden='true']",
    ".sr-only",
    ".hide-accessible",
    ".invisible-element",
    ".visually-hidden",
    ".visible-interaction",   # licznik odsłon / widget interaction, nie treść
    ".descArticles",          # "artykuły" - zdublowany licznik przy każdej sekcji
    ".skip-link",
    "#wmfc_quickAccessNav",
    "[id$='quickAccessNav']", # id zmienia się losowo (np. srxk_quickAccessNav)
]

# Krótkie frazy-kontrolki UI, które nie mają jednej stałej klasy, ale zawsze
# wyglądają tak samo i nigdy nie są treścią merytoryczną. Dopasowanie jest
# case-insensitive i po pełnej linii (nie substring), żeby nie ucinać
# fragmentów prawdziwych zdań.
LINE_STOPLIST = {
    "pomiń baner",
    "pomiń do treści",
    "wszystkie",
    "popularne",
    "artykuły",
    "ukryty",
    "menu",
    "zaloguj",
    "wersja kontrastowa",
    "a",
    "en",
    "hidden",
    "skip to content",
}

# Próg wykrywania boilerplate między stronami: jeśli dana linia pojawia się
# na więcej niż tym % zeskrapowanych stron, traktujemy ją jako element
# szablonu (nawigacja, stopka, powtarzalne widżety), a nie treść artykułu.
# Dotyczy tylko krótszych linii - długi, wielokrotnie powtórzony akapit to
# raczej realna treść (np. ta sama klauzula na wielu podstronach), więc go
# nie ruszamy.
BOILERPLATE_RATIO = 0.3
BOILERPLATE_MAX_WORDS = 6


def is_same_domain(url: str) -> bool:
    return urlparse(url).netloc in ALLOWED_DOMAINS


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="", query="").geturl()


LOCALE_PATTERN = re.compile(r"^/[a-z]{2}(_[a-z]{2})?/", re.IGNORECASE)
SKIP_PATTERNS = ("/c/portal/login", "/c/portal/logout")


def should_skip(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(pattern in path for pattern in SKIP_PATTERNS):
        return True
    if LOCALE_PATTERN.match(path):
        return True
    if path.count("/journal_content/") > 1:
        return True
    return False


def strip_noise(content):
    """Usuwa elementy dekoracyjne/dostępnościowe zanim wyciągniemy tekst."""
    for tag in content(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    for selector in NOISE_SELECTORS:
        for el in content.select(selector):
            el.decompose()
    return content


def extract_text(soup: BeautifulSoup):
    content = (
        soup.find(id="main-content")
        or soup.find("main")
        or soup.find("article")
        or soup.find("body")
    )
    if content is None:
        return None

    content = strip_noise(content)

    text = content.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    # filtr fraz-kontrolek
    lines = [line for line in lines if line.lower() not in LINE_STOPLIST]

    # deduplikacja sąsiadujących powtórzeń (np. ten sam nagłówek złapany
    # dwa razy przez dwie zagnieżdżone wersje responsywne obok siebie)
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return "\n".join(deduped) if deduped else None


def extract_wikipedia_text(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    content = soup.find("div", id="mw-content-text")
    if content is None:
        return None

    for selector in [
        ".mw-editsection", "sup.reference", ".reflist", ".navbox", ".ambox",
        ".infobox", "table.metadata", ".mw-references-wrap", "style",
        "#toc", ".toc", ".hatnote", "sup", ".mw-authority-control",
        ".noprint", ".mw-empty-elt",
    ]:
        for el in content.select(selector):
            el.decompose()

    block_tags = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "caption", "dd", "dt", "blockquote"]

    lines = []
    for el in content.find_all(block_tags):
        if el.find_parent(block_tags) is not None:
            continue
        text = el.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        if text:
            lines.append(text)

    return "\n".join(lines)


def remove_boilerplate(pages):
    """
    pages: lista (url, text) już po per-page czyszczeniu.
    Usuwa krótkie linie powtarzające się na dużym % stron - to prawie zawsze
    resztki nawigacji/stopki/widżetów, które przeciekły mimo filtrów wyżej.
    """
    total_pages = len(pages)
    if total_pages <= 1:
        return pages

    line_doc_count = Counter()
    for _, text in pages:
        unique_lines = set(text.splitlines())
        for line in unique_lines:
            line_doc_count[line] += 1

    threshold = max(2, int(total_pages * BOILERPLATE_RATIO))

    def is_boilerplate(line: str) -> bool:
        if len(line.split()) > BOILERPLATE_MAX_WORDS:
            return False
        return line_doc_count[line] >= threshold

    cleaned_pages = []
    for url, text in pages:
        kept = [line for line in text.splitlines() if not is_boilerplate(line)]
        cleaned_pages.append((url, "\n".join(kept)))
    return cleaned_pages


def scrape_wikipedia():
    results = []
    for url in WIKIPEDIA_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[BŁĄD - Wikipedia] {url} -> {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = extract_wikipedia_text(soup)

        if page_text is None:
            print(f"[POMINIĘTO - brak treści Wikipedia] {url}")
            continue

        results.append((url, page_text))
        print(f"[Wikipedia] pobrano: {url}")
        time.sleep(DELAY)
    return results


def crawl():
    visited = set()
    queue = deque(START_URLS)
    count = 0
    pages = []  # (url, text) - zbieramy w pamięci, żeby móc odfiltrować boilerplate na końcu

    while queue:
        if MAX_PAGES and count >= MAX_PAGES:
            break

        url = queue.popleft()
        url = clean_url(url)
        if url in visited:
            continue
        visited.add(url)

        if should_skip(url):
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"[BŁĄD] {url} -> {e}")
            continue

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = extract_text(soup)

        if page_text is None:
            FALLBACK_USED.append(url)
            print(f"[POMINIĘTO - brak main-content] {url}")
        else:
            pages.append((url, page_text))
            count += 1
            print(f"[{count}] pobrano: {url}")

        for a in soup.find_all("a", href=True):
            link = urljoin(url, a["href"])
            link = clean_url(link)
            if is_same_domain(link) and link not in visited and not should_skip(link):
                queue.append(link)

        time.sleep(DELAY)

    pages.extend(scrape_wikipedia())

    # drugi przebieg: usuń linie-szablony powtarzające się na wielu stronach
    pages = remove_boilerplate(pages)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for url, text in pages:
            if not text.strip():
                continue
            f.write(f"\n\n{'='*80}\nURL: {url}\n{'='*80}\n\n")
            f.write(text)

    print(f"\nZapisano {len(pages)} stron do pliku: {OUTPUT_FILE}")
    print(f"Pominięto (brak main-content) {len(FALLBACK_USED)} stron:")
    for u in FALLBACK_USED:
        print(f"  - {u}")


if __name__ == "__main__":
    crawl()
