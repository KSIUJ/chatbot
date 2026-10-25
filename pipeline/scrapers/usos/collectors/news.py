"""
Aktualnosci USOSweb (news/search - z kluczem aplikacji): artykuly
opublikowane w ostatnich NEWS_DAYS dniach albo wciaz aktualne (data
waznosci w przyszlosci) - USOS zwraca tylko artykuly jeszcze widoczne. Brane sa
artykuly calej uczelni (UJ) i wydzialu. Tresc z HTML-a jako Markdown, z data publikacji
w tekscie - pytania o terminy ("do kiedy wnioski o stypendium") jej potrzebuja.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from src.backend.rag.sources.usos.dataset import NewsAttributes, NewsRecord

from ..api import fields
from ..context import Context
from ..text import document, format_date, parse_date, parse_datetime, pick, pick_markdown

NAME = "news"
NEEDS_CONSUMER = True

NEWS_DAYS = 365
ARTICLE_FIELDS = fields(
    "id", "publication_date", "title", "headline_html", "content_html", "expiry_date", "category", "faculty",
)
NEWS_URL_ACTION = "news/default"
UNIVERSITY_FACULTIES = ("", "UJ")


def news_record(ctx: Context, article: dict) -> NewsRecord | None:
    news_id = str(article.get("id") or "")
    title = pick(article.get("title"))
    body = pick_markdown(article.get("content_html"), heading_offset=1) or pick_markdown(
        article.get("headline_html"), heading_offset=1
    )
    if not news_id or not title or not body:
        return None
    published = parse_datetime(article.get("publication_date"))
    expiry = parse_date(article.get("expiry_date"))
    category = pick((article.get("category") or {}).get("name"))
    faculty = pick((article.get("faculty") or {}).get("name"))
    meta = [
        f"Opublikowano: {format_date(published)}" if published else "",
        f"Aktualne do: {format_date(expiry)}" if expiry else "",
        f"Kategoria: {category}" if category else "",
        f"Jednostka: {faculty}" if faculty else "",
    ]
    return NewsRecord(
        id=f"news:{news_id}",
        kind="news",
        title=title,
        # adres wspolny dla aktualnosci, z kotwica - kazdy rekord ma wlasny (zrodla odpowiedzi)
        url=f"{ctx.usosweb(NEWS_URL_ACTION)}#news-{news_id}",
        lang="pl",
        updated_at=published.replace(tzinfo=ctx.tz) if published else None,
        content=document(f"# {title}", "\n".join(line for line in meta if line), body),
        attributes=NewsAttributes(news_id=news_id, category=category, faculty=faculty, expiry_date=expiry),
    )


def collect(ctx: Context) -> Iterator[NewsRecord]:
    since = ctx.today - timedelta(days=NEWS_DAYS)
    for item in ctx.api.pages(
        "services/news/search",
        num=100,
        from_date=since.isoformat(),
        fields=f"items[article[{ARTICLE_FIELDS}]]|next_page",
    ):
        article = (item or {}).get("article") if isinstance(item, dict) else None
        if not isinstance(article, dict):
            continue
        # aktualnosci calej uczelni i wydzialu; innych wydzialow (np. ich deklaracje
        # przedmiotow) studentow WMI nie dotycza
        fac_id = str((article.get("faculty") or {}).get("id") or "")
        if fac_id not in UNIVERSITY_FACULTIES and not ctx.in_faculty(fac_id):
            continue
        record = news_record(ctx, article)
        if record is not None:
            yield record
