import os

from ..RAG.context_builder import build_context
from .client import chat

SYSTEM_PROMPT = (
    "Jestes asystentem Wydzialu Matematyki i Informatyki UJ. ZASADY:\n"
    "1. Odpowiadaj ZAWSZE i wylacznie po polsku. Nigdy nie uzywaj chinskiego "
    "ani innego jezyka, nawet jesli kontekst jest w innym jezyku lub zawiera "
    "polamany tekst.\n"
    "2. Opieraj sie na sekcjach KONTEKST TEKSTOWY i PASUJACE PLIKI. Nie zmyslaj "
    "tresci, ktorej tam nie ma.\n"
    "3. Jesli jest sekcja PRACOWNIK, to ona zawiera odpowiedz na pytanie o te "
    "osobe (stanowisko, pokoj, dyzury, e-mail, zainteresowania). Nie szukaj "
    "tych danych w pozostalych sekcjach.\n"
    "4. Sekcja ZRODLA OFICJALNE ma pierwszenstwo: przy pytaniach o pracownikow, "
    "dyzury, pokoje, regulaminy i terminy opieraj sie wylacznie na niej. "
    "MATERIALY STUDENCKIE traktuj jako pomocnicze i nie cytuj z nich danych "
    "kontaktowych ani zasad organizacyjnych.\n"
    "5. Jesli w PASUJACE PLIKI sa materialy pasujace do pytania, WSKAZ je "
    "uzytkownikowi po nazwie - nawet jesli nie znasz ich tresci. To czesto "
    "skany zadan/notatek, wiec sam plik jest odpowiedzia i zostanie dolaczony.\n"
    "6. Dopiero jesli naprawde nic nie pasuje, powiedz krotko, ze nie masz tego "
    "w materialach. Odpowiadaj rzeczowo i zwiezle."
)


def _format_files(files: list[str]) -> str:
    lines = []
    for path in files:
        name = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        lines.append(f"- {name} (folder: {parent})")
    return "\n".join(lines)


def answer(query: str, k_mordor: int = 5, k_other: int = 5) -> dict:
    context, files = build_context(query, k_mordor=k_mordor, k_other=k_other)

    parts = []
    if context.strip():
        parts.append(f"KONTEKST TEKSTOWY:\n{context}")
    if files:
        parts.append(
            "PASUJACE PLIKI (materialy/skany - tresci moze nie byc, ale mozesz "
            "je wskazac uzytkownikowi):\n" + _format_files(files)
        )
    if not parts:
        parts.append("(Brak pasujacego kontekstu i plikow w bazie.)")

    user_message = "\n\n".join(parts) + f"\n\nPYTANIE: {query}\n\nOdpowiedz po polsku."

    reply = chat(system=SYSTEM_PROMPT, user=user_message)
    return {"answer": reply, "files": files}


def main() -> None:
    import sys

    query = " ".join(sys.argv[1:]).strip() or "jakie sa zasady zaliczenia?"
    result = answer(query)

    print("\n=== ODPOWIEDZ ===\n")
    print(result["answer"])
    if result["files"]:
        print("\n=== DOLACZONE PLIKI ===")
        for path in result["files"]:
            print(f" - {path}")


if __name__ == "__main__":
    main()
