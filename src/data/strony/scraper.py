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
    "https://knmf.im.uj.edu.pl/",
]

ALLOWED_DOMAINS = {urlparse(u).netloc for u in START_URLS}
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = REPO_ROOT / "data" / "strony" / "webiste_data.txt"
DELAY = 0.2
MAX_PAGES = 1000

WIKIPEDIA_URLS = [
    "https://pl.wikipedia.org/wiki/Wydzia%C5%82_Matematyki_i_Informatyki_Uniwersytetu_Jagiello%C5%84skiego",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

FALLBACK_USED = []

# klasy do pominiecia
NOISE_SELECTORS = [
    "[aria-hidden='true']",
    ".sr-only",
    ".hide-accessible",
    ".invisible-element",
    ".visually-hidden",
    ".visible-interaction",
    ".descArticles",
    ".skip-link",
    "#wmfc_quickAccessNav",
    "[id$='quickAccessNav']"
]

# frazy do pominiecia
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

# zmienne do liczenia ilosci wstapienia frazy (jesli wystepuje na duzej ilosci stron to znaczy ze fragment boilerplatea)
BOILERPLATE_RATIO = 0.3
BOILERPLATE_MAX_WORDS = 6

# zmienne do usuwania menu ktore sie powialy na min ilosci stron
MENU_ITEM_MAX_WORDS = 4
MENU_ITEM_MIN_PAGES = 3

# od ilu slow linia liczy sie jako tresc
DEDUPE_MIN_WORDS = 8

MIN_CONTENT_WORDS = 15


def is_same_domain(url: str) -> bool:
    return urlparse(url).netloc in ALLOWED_DOMAINS


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(
        scheme="https",
        netloc=parsed.netloc.lower(),
        fragment="",
        query="",
    ).geturl()

# usuwa niepotrzebne jezyki np /en/
LOCALE_PATTERN = re.compile(r"^/[a-z]{2}(_[a-z]{2})?/", re.IGNORECASE)
SKIP_PATTERNS = ("/c/portal/login", "/c/portal/logout")

def should_skip(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(pattern in path for pattern in SKIP_PATTERNS):
        return True
    if LOCALE_PATTERN.match(path):
        return True
    # powtarzajacy sie segment journal_content (linkuje do siebie w kolo)
    if path.count("/journal_content/") > 1:
        return True
    return False

# elementy blokowe (do tworzenia spojnych akapitow)
BLOCK_TAGS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "caption", "dd", "dt", "blockquote", "figcaption"]


def _clean_spacing(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([„«])\s+", r"\1", text)
    text = re.sub(r"\s+([”»])", r"\1", text)
    return text


def get_block_text(content):
    # wyciaga tekst blok po bloku (p/li/h*) zeby link w srodku zdania go nie rozrywal
    lines = []
    for el in content.find_all(BLOCK_TAGS):
        if el.find_parent(BLOCK_TAGS) is not None:
            continue
        text = el.get_text(separator=" ", strip=True)
        text = _clean_spacing(text)
        if text:
            lines.append(text)

    if not lines:
        text = content.get_text(separator="\n")
        lines = [_clean_spacing(l) for l in text.splitlines() if l.strip()]

    return lines


def dedupe_repeated_blocks(lines):
    # usuwa caly blok linii, jesli powtarza sie bezposrednio po sobie (mobile+desktop menu)
    n = len(lines)
    result = []
    i = 0
    while i < n:
        matched = False
        max_block = (n - i) // 2
        for block_len in range(max_block, 0, -1):
            if lines[i:i + block_len] == lines[i + block_len:i + 2 * block_len]:
                result.extend(lines[i:i + block_len])
                i += 2 * block_len
                matched = True
                break
        if not matched:
            result.append(lines[i])
            i += 1
    return result


def strip_noise(content):
    # usuwa niepotrzebne elementy strony
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

    lines = get_block_text(content)

    lines = [line for line in lines if line.lower() not in LINE_STOPLIST]

    lines = dedupe_repeated_blocks(lines)

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

    # usuwa elementy niebedace trescia
    for selector in [
        ".mw-editsection", "sup.reference", ".reflist", ".navbox", ".ambox",
        ".infobox", "table.metadata", ".mw-references-wrap", "style",
        "#toc", ".toc", ".hatnote", "sup", ".mw-authority-control",
        ".noprint", ".mw-empty-elt",
    ]:
        for el in content.select(selector):
            el.decompose()

    lines = get_block_text(content)
    return "\n".join(lines)


def remove_boilerplate(pages):
    # usuwa krotkie linie powtarzajace sie na wielu stronach
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
        word_count = len(line.split())
        count = line_doc_count[line]
        if word_count <= BOILERPLATE_MAX_WORDS and count >= threshold:
            return True
        if word_count <= MENU_ITEM_MAX_WORDS and count >= MENU_ITEM_MIN_PAGES:
            return True
        return False

    cleaned_pages = []
    for url, text in pages:
        kept = [line for line in text.splitlines() if not is_boilerplate(line)]
        cleaned_pages.append((url, "\n".join(kept)))
    return cleaned_pages


def _normalize(line: str) -> str:
    return " ".join(line.lower().split())


def dedupe_content_across_pages(pages):
    # pozbywa sie duplikatow na wielu stronach
    line_pages = {}
    for url, text in pages:
        for line in text.splitlines():
            if len(line.split()) < DEDUPE_MIN_WORDS:
                continue
            key = _normalize(line)
            line_pages.setdefault(key, set()).add(url)

    canonical_url = {}
    for key, urls in line_pages.items():
        if len(urls) > 1:
            canonical_url[key] = max(urls, key=lambda u: len(urlparse(u).path))

    cleaned_pages = []
    for url, text in pages:
        kept = []
        for line in text.splitlines():
            key = _normalize(line) if len(line.split()) >= DEDUPE_MIN_WORDS else None
            if key in canonical_url and canonical_url[key] != url:
                continue  # duplikat - trzymamy go tylko na stronie kanonicznej
            kept.append(line)
        cleaned_pages.append((url, "\n".join(kept)))
    return cleaned_pages


def drop_thin_hub_pages(pages):
    # strony z bardzo mala iloscia slow nie sa zapisywane (glownie strony z samymi linkami)
    kept, dropped = [], []
    for url, text in pages:
        word_count = len(text.split())
        if word_count < MIN_CONTENT_WORDS:
            dropped.append((url, word_count))
        else:
            kept.append((url, text))
    return kept, dropped


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
    pages = []

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

    wiki_pages = scrape_wikipedia()

    pages = remove_boilerplate(pages)
    pages = dedupe_content_across_pages(pages)
    pages = pages + wiki_pages

    pages, dropped_hubs = drop_thin_hub_pages(pages)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for url, text in pages:
            if not text.strip():
                continue
            # oddzielanie stron
            #f.write(f"\n\n{'='*80}\nURL: {url}\n{'='*80}\n\n")
            f.write(text)

    print(f"\nZapisano {len(pages)} stron do pliku: {OUTPUT_FILE}")
    print(f"Pominięto (brak main-content) {len(FALLBACK_USED)} stron:")
    for u in FALLBACK_USED:
        print(f"  - {u}")
    print(f"Pominięto jako puste huby/listingi po deduplikacji ({len(dropped_hubs)}):")
    for u, wc in dropped_hubs:
        print(f"  - {u} ({wc} słów)")


if __name__ == "__main__":
    crawl()