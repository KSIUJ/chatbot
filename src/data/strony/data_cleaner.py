"""
Czyszczenie długiego pliku tekstowego z crawlera:
- usuwa boilerplate powtarzające się MIĘDZY dokumentami (menu, stopki) - filtr częstości
- usuwa strukturalny szum WEWNĄTRZ dokumentu (kalendarz, etykiety nawigacyjne) - filtr wzorcowy
- usuwa duplikaty artykułów 1:1
- opcjonalnie: wykrywa near-duplicate artykuły przez MinHash (pip install datasketch)

Rozpoznaje format plików z separatorami:
    ================================================================================
    URL: https://...
    ================================================================================
    <treść strony>
Jeśli separatorów brak, traktuje cały plik jako jeden dokument.
"""

import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INPUT_FILE = REPO_ROOT / "data" / "strony" / "webiste_data.txt"
OUTPUT_FILE = REPO_ROOT / "data" / "strony" / "webiste_data_clean.txt"

URL_BLOCK_RE = re.compile(
    r"={10,}\s*\nURL:\s*(?P<url>\S+)\s*\n={10,}\s*\n(?P<content>.*?)(?=\n={10,}\s*\nURL:|\Z)",
    re.DOTALL,
)

# --- Filtr wzorcowy (pattern-based) dla szumu wewnątrz-dokumentowego ---

MONTH_ABBREV = {
    "sty", "lut", "mar", "kwi", "maj", "cze",
    "lip", "sie", "wrz", "paź", "lis", "gru",
}

# Etykiety nawigacyjne specyficzne dla tego serwisu.
# UZUPEŁNIAJ tę listę po każdym przeglądzie wyniku - to jest strojenie pod konkretną stronę.
NAV_LABELS = {
    "wszystkie", "artykuły", "popularne", "więcej", "ukryty",
    "facebook", "youtube", "instagram", "linkedin", "spotify",
    "flickr", "bluesky", "x",
}

PURE_NUMBER_RE = re.compile(r"^\d{1,4}$")
PURE_DASH_RE = re.compile(r"^-+$")


def is_structural_noise(norm_line: str) -> bool:
    """
    Rozpoznaje linie, które PRAWIE NA PEWNO są szumem strukturalnym
    (kalendarz, nawigacja) niezależnie od tego, jak często występują
    w korpusie. Celowo konserwatywne - lepiej przepuścić coś wątpliwego
    niż wyciąć realną treść.
    """
    if PURE_NUMBER_RE.match(norm_line):
        return True
    if PURE_DASH_RE.match(norm_line):
        return True
    if norm_line in MONTH_ABBREV:
        return True
    if norm_line in NAV_LABELS:
        return True
    return False


# --- Podział na dokumenty ---

def split_into_documents(text: str, split_regex: str | None = None) -> list[str]:
    matches = list(URL_BLOCK_RE.finditer(text))
    if matches:
        return [m.group("content").strip() for m in matches if m.group("content").strip()]

    if split_regex:
        parts = re.split(split_regex, text)
        return [p for p in parts if p.strip()]

    parts = re.split(r"\n\s*\n\s*\n+", text)
    return [p for p in parts if p.strip()]


def normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def build_line_frequency(documents: list[str]) -> Counter:
    """Liczy w ilu OSOBNYCH dokumentach dana linia się pojawia."""
    freq = Counter()
    for doc in documents:
        seen_in_this_doc = set()
        for line in doc.splitlines():
            norm = normalize_line(line)
            if not norm:
                continue
            if norm not in seen_in_this_doc:
                freq[norm] += 1
                seen_in_this_doc.add(norm)
    return freq


def remove_boilerplate(
    documents: list[str],
    line_freq: Counter,
    n_docs: int,
    max_line_len: int = 60,
    freq_threshold: float = 0.15,
    min_docs_for_stats: int = 2,
) -> list[str]:
    """
    Usuwa linię jeśli SPEŁNIA KTÓRYKOLWIEK z warunków:
    A) jest krótka i częsta w wielu dokumentach (klasyczny boilerplate: menu, stopka)
    B) pasuje do rozpoznanego wzorca szumu strukturalnego (kalendarz, etykiety nawigacyjne)
       - to działa NAWET dla pojedynczego dokumentu, bez potrzeby statystyk częstości
    """
    cleaned_docs = []
    use_freq_filter = n_docs >= min_docs_for_stats

    for doc in documents:
        kept_lines = []
        for line in doc.splitlines():
            norm = normalize_line(line)
            if not norm:
                kept_lines.append(line)
                continue

            if is_structural_noise(norm):
                continue

            is_short = len(norm) <= max_line_len
            is_frequent = use_freq_filter and (line_freq[norm] / n_docs) >= freq_threshold

            if is_short and is_frequent:
                continue

            kept_lines.append(line)

        cleaned_docs.append("\n".join(kept_lines))
    return cleaned_docs


def dedupe_exact(documents: list[str]) -> list[str]:
    seen_hashes = set()
    unique_docs = []
    for doc in documents:
        norm = re.sub(r"\s+", " ", doc).strip().lower()
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique_docs.append(doc)
    return unique_docs


def dedupe_near_duplicates(documents: list[str], threshold: float = 0.85) -> list[str]:
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        print("Pomijam near-duplicate detection: pip install datasketch")
        return documents

    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    unique_docs = []

    for i, doc in enumerate(documents):
        words = re.findall(r"\w+", doc.lower())
        shingles = {" ".join(words[j:j + 5]) for j in range(max(len(words) - 4, 1))}

        m = MinHash(num_perm=128)
        for s in shingles:
            m.update(s.encode("utf-8"))

        if lsh.query(m):
            continue
        lsh.insert(f"doc_{i}", m)
        unique_docs.append(doc)

    return unique_docs


def main():
    parser = argparse.ArgumentParser(description="Czyszczenie tekstu z crawlera")
    parser.add_argument("--split-regex", default=None)
    parser.add_argument("--max-line-len", type=int, default=60)
    parser.add_argument("--freq-threshold", type=float, default=0.15)
    parser.add_argument("--min-docs-for-stats", type=int, default=2)
    parser.add_argument("--near-dup", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku wejściowego: {INPUT_FILE}")

    output_path = Path(args.output) if args.output else OUTPUT_FILE

    text = INPUT_FILE.read_text(encoding="utf-8")
    documents = split_into_documents(text, args.split_regex)
    print(f"Wczytano: {INPUT_FILE}")
    print(f"Znaleziono {len(documents)} dokumentów/bloków")

    documents = dedupe_exact(documents)
    print(f"Po usunięciu duplikatów 1:1: {len(documents)}")

    if args.near_dup:
        documents = dedupe_near_duplicates(documents)
        print(f"Po usunięciu near-duplicate: {len(documents)}")

    line_freq = build_line_frequency(documents)
    documents = remove_boilerplate(
        documents, line_freq, n_docs=len(documents),
        max_line_len=args.max_line_len,
        freq_threshold=args.freq_threshold,
        min_docs_for_stats=args.min_docs_for_stats,
    )

    result = "\n\n".join(d.strip() for d in documents if d.strip())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result, encoding="utf-8")
    print(f"Zapisano wynik do {output_path}")


if __name__ == "__main__":
    main()