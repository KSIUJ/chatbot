import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
from pathlib import Path


START_URL = "https://matinf.uj.edu.pl/"
DOMAIN = urlparse(START_URL).netloc  # matinf.uj.edu.pl
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = REPO_ROOT / "data" / "strony" / "webiste_data.txt"
DELAY = 0.5
MAX_PAGES = 300

WIKIPEDIA_URLS = [
    "https://pl.wikipedia.org/wiki/Wydzia%C5%82_Matematyki_i_Informatyki_Uniwersytetu_Jagiello%C5%84skiego",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

# licznik pomienietych stron
FALLBACK_USED = []


def is_same_domain(url: str) -> bool:
    return urlparse(url).netloc == DOMAIN


def clean_url(url: str) -> str:
    # usuwa smieci z linka
    parsed = urlparse(url)
    return parsed._replace(fragment="", query="").geturl()



LANGUAGE_PREFIXES = ("/pl/", "/pl_pl/", "/en/", "/en_gb/")

SKIP_PATTERNS = ("/c/portal/login", "/c/portal/logout")


def should_skip(url: str) -> bool:
    path = urlparse(url).path.lower()

    # pomin linki logowania/wylogowania
    if any(pattern in path for pattern in SKIP_PATTERNS):
        return True

    # pomin wersje z prefiksem jezykowym
    if path.startswith(LANGUAGE_PREFIXES):
        return True

    return False


def extract_text(soup: BeautifulSoup):
    # usun skrypty i style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # zostaw tylko main content strony
    content = soup.find(id="main-content")

    if content is None:
        # jak nie ma main-content pomijamy strone
        return None

    text = content.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)

def extract_wikipedia_text(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    content = soup.find("div", id="mw-content-text")
    if content is None:
        return None

    # usun elementy ktore nie sa trescia merytoryczna
    for selector in [
        ".mw-editsection",        # linki
        "sup.reference",          # przypisy
        ".reflist",                # lista przypisow na dole
        ".navbox",                 # boksy nawigacyjne
        ".ambox",                  # komunikaty ostrzegawcze
        ".infobox",                # infobox
        "table.metadata",
        ".mw-references-wrap",
        "style",
        "#toc", ".toc",            # spis tresci
        ".hatnote",
        "sup",
        ".mw-authority-control",
        ".noprint",
        ".mw-empty-elt",
    ]:
        for el in content.select(selector):
            el.decompose()

    # elementy blokowe (do tworzenia spojnych akapitow)
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

def scrape_wikipedia(f):
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

        f.write(f"\n\n{'='*80}\nURL: {url}\n{'='*80}\n\n")
        f.write(page_text)
        print(f"[Wikipedia] pobrano: {url}")

        time.sleep(DELAY)

def crawl():
    visited = set()
    queue = deque([START_URL])
    count = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
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
                continue  # pomin pdf-y, obrazki itp.

            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = extract_text(soup)

            if page_text is None:
                # Brak id="main-content"
                FALLBACK_USED.append(url)
                print(f"[POMINIĘTO - brak main-content] {url}")
            else:
                # zapisz tekst strony
                f.write(f"\n\n{'='*80}\nURL: {url}\n{'='*80}\n\n")
                f.write(page_text)
                count += 1
                print(f"[{count}] pobrano: {url}")

            # znajdz linki i dodaj do kolejki
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                link = clean_url(link)
                if is_same_domain(link) and link not in visited and not should_skip(link):
                    queue.append(link)

            time.sleep(DELAY)

        # wikipedia do tego samego pliku
        scrape_wikipedia(f)

    print(f"\nZapisano {count} stron do pliku: {OUTPUT_FILE}")
    print(f"Pominięto (brak main-content) {len(FALLBACK_USED)} stron:")
    for u in FALLBACK_USED:
        print(f"  - {u}")


if __name__ == "__main__":
    crawl()