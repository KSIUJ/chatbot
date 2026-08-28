from .lexical import LexicalIndex, tokenize

DEFAULT_LIMIT = 2
MIN_STEM = 4


def _fleeting_e_stem(token: str) -> str | None:
    if len(token) < 5:
        return None
    if token.endswith("iec"):
        return token[:-3] + "c"
    if token.endswith("ek"):
        return token[:-2] + "k"
    if token.endswith("ec"):
        return token[:-2] + "c"
    return None


class StaffIndex:
    def __init__(self, names: list[str], lexical: LexicalIndex):
        self.lexical = lexical
        self.name_tokens: set[str] = set()
        self.surnames: set[str] = set()
        self._stems: dict[str, str] = {}

        for name in names:
            parts = tokenize(name or "")
            if not parts:
                continue
            self.name_tokens.update(parts)
            self.surnames.update(parts[1:] or parts)

        for token in self.name_tokens:
            if len(token) >= MIN_STEM:
                self._stems.setdefault(token, token)
            stem = _fleeting_e_stem(token)
            if stem and len(stem) >= MIN_STEM:
                self._stems.setdefault(stem, token)

    @classmethod
    def from_collection(cls, collection, lexical: LexicalIndex) -> "StaffIndex":
        got = collection.get(where={"source": "usos"}, include=["metadatas"])
        names = [(m or {}).get("employee_name") or "" for m in got.get("metadatas", [])]
        return cls(names, lexical)

    def _canonical(self, token: str) -> str | None:
        if token in self.name_tokens:
            return token
        if len(token) < MIN_STEM:
            return None

        best_stem = None
        for stem in self._stems:
            if token.startswith(stem):
                if best_stem is None or len(stem) > len(best_stem):
                    best_stem = stem
        return self._stems[best_stem] if best_stem else None

    def lookup(self, query: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        matched = [c for c in (self._canonical(t) for t in tokenize(query)) if c]
        if not any(c in self.surnames for c in matched):
            return []

        return self.lexical.search(matched, sources=("usos",), limit=limit)
