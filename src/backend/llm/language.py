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


# Stala odmowa, gdy odpowiedz modelu to sam znacznik [[NARUSZENIE]] (pusta po
# jego zdjeciu) - uzytkownik nie dostaje pustej odpowiedzi ani bledu. Jak prompt
# (zasada 18): odmowa i informacja, ze proba trafila do zarzadu (incydent).
REFUSAL: dict[Language, str] = {
    "pl": "Nie mogę pomóc w tej prośbie. Mogę odpowiadać na pytania o UJ, "
          "Wydział Matematyki i Informatyki oraz KSI. "
          "Próba obejścia zasad została odnotowana i zgłoszona do zarządu KSI.",
    "en": "I can't help with this request. I can answer questions about the Jagiellonian "
          "University, the Faculty of Mathematics and Computer Science and KSI. "
          "This attempt to bypass the rules has been recorded and reported to the KSI board.",
    "de": "Bei dieser Anfrage kann ich nicht helfen. Ich beantworte Fragen zur "
          "Jagiellonen-Universität, zur Fakultät für Mathematik und Informatik und zu KSI. "
          "Dieser Versuch, die Regeln zu umgehen, wurde protokolliert und dem KSI-Vorstand gemeldet.",
    "es": "No puedo ayudar con esta solicitud. Puedo responder preguntas sobre la Universidad "
          "Jaguelónica, la Facultad de Matemáticas e Informática y KSI. "
          "Este intento de eludir las reglas ha quedado registrado y se ha notificado a la junta de KSI.",
    "fr": "Je ne peux pas aider avec cette demande. Je peux répondre aux questions sur "
          "l'Université Jagellonne, la Faculté de mathématiques et d'informatique et KSI. "
          "Cette tentative de contourner les règles a été enregistrée et signalée au bureau de KSI.",
    "it": "Non posso aiutare con questa richiesta. Posso rispondere a domande sull'Università "
          "Jagellonica, sulla Facoltà di Matematica e Informatica e su KSI. "
          "Questo tentativo di aggirare le regole è stato registrato e segnalato al direttivo di KSI.",
    "uk": "Я не можу допомогти з цим запитом. Я можу відповідати на питання про "
          "Ягеллонський університет, факультет математики та інформатики і KSI. "
          "Цю спробу обійти правила зафіксовано й повідомлено правлінню KSI.",
}


def parse_language(value: str | None) -> Language | None:
    """Kod jezyka z listy LANGUAGES albo None dla czegokolwiek innego."""
    for language in LANGUAGES:
        if value == language:
            return language
    return None
