"""Format zbioru stron (data/uj_pages/, takze strony KSI w data/ksi/)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...core.datasets import Record

# Rodzaj witryny - decyduje, jak wiarygodna jest strona i jak ja podpisac:
# faculty - wydzial (matinf.uj.edu.pl), uj - pozostale strony UJ, usosownia -
# instrukcje USOS, student_group - kola naukowe, ksi - strony KSI,
# wikipedia, other.
PageCategory = Literal["faculty", "uj", "usosownia", "student_group", "ksi", "wikipedia", "other"]


class PageAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # host witryny, np. matinf.uj.edu.pl
    site: str = Field(min_length=1)
    category: PageCategory
    # sciezka w menu witryny, od ogolu do szczegolu, np. ["Studenci", "Formularze"]
    breadcrumbs: list[str] = Field(default_factory=list)
    # typ zrodla tresci: text/html dla stron, application/pdf itd. dla plikow
    media_type: str = "text/html"


class PageRecord(Record):
    """Strona albo plik (pdf, docx) z witryny; content = tresc w Markdownie z naglowkami."""

    kind: Literal["page", "document"]
    url: str
    attributes: PageAttributes
