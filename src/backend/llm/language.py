"""Jezyki interfejsu i odpowiedzi - te same co w Keycloaku KSI (ChatRequest.language)."""

from typing import Literal, get_args

Language = Literal["pl", "en", "de", "es", "fr", "it", "uk"]

LANGUAGES: tuple[Language, ...] = get_args(Language)

DEFAULT_LANGUAGE: Language = "pl"

# Jezyk odpowiedzi w regule 1 promptu systemowego
LANGUAGE_NAMES: dict[Language, str] = {
    "pl": "po polsku",
    "en": "po angielsku (English)",
    "de": "po niemiecku (Deutsch)",
    "es": "po hiszpansku (español)",
    "fr": "po francusku (français)",
    "it": "po wlosku (italiano)",
    "uk": "po ukrainsku (українською)",
}

# Ostatnia linia wiadomosci uzytkownika - w jezyku odpowiedzi
ANSWER_IN: dict[Language, str] = {
    "pl": "Odpowiedz po polsku.",
    "en": "Answer in English.",
    "de": "Antworte auf Deutsch.",
    "es": "Responde en español.",
    "fr": "Réponds en français.",
    "it": "Rispondi in italiano.",
    "uk": "Відповідай українською.",
}


def parse_language(value: str | None) -> Language | None:
    """Kod jezyka z listy LANGUAGES albo None dla czegokolwiek innego."""
    for language in LANGUAGES:
        if value == language:
            return language
    return None
