from contextlib import contextmanager
import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Iterator


STOP_WORDS = {
    "a", "about", "after", "all", "am", "an", "and", "are", "as", "at", "be",
    "can", "could", "do", "does", "for", "from", "give", "has", "have", "help",
    "how", "i", "in", "is", "it", "me", "of", "on", "or", "please", "show",
    "tell", "that", "the", "their", "there", "this", "to", "was", "what", "when",
    "where", "which", "who", "why", "with", "would", "you", "offer", "offers",
    "appear", "indexed", "pages", "published", "information",
}


class KnowledgeBase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents
                USING fts5(title, content, url UNINDEXED, source UNINDEXED)
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def count(self) -> int:
        with self._connect() as connection:
            return connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def counts_by_source(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source, COUNT(*) AS page_count FROM documents GROUP BY source"
            ).fetchall()
        return {row["source"]: row["page_count"] for row in rows}

    def replace_all(self, pages: list[dict[str, str]]) -> None:
        unique_pages = []
        seen_urls: set[tuple[str, str]] = set()
        seen_content: set[tuple[str, bytes]] = set()
        for page in pages:
            url_key = (page["source"], page["url"])
            content_key = (
                page["source"],
                hashlib.sha256(page["content"].casefold().encode("utf-8")).digest(),
            )
            if url_key in seen_urls or content_key in seen_content:
                continue
            seen_urls.add(url_key)
            seen_content.add(content_key)
            unique_pages.append(page)

        with self._connect() as connection:
            connection.execute("DELETE FROM documents")
            connection.executemany(
                "INSERT INTO documents (title, content, url, source) VALUES (?, ?, ?, ?)",
                [
                    (
                        page["title"],
                        page["content"],
                        page["url"],
                        page["source"],
                    )
                    for page in unique_pages
                ],
            )

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        normalized_query = query.casefold()
        source_filter = None
        if "wasalt" in normalized_query:
            source_filter = "Wasalt"
        elif "darglobal" in normalized_query or "dar global" in normalized_query:
            source_filter = "DarGlobal"

        terms = [
            term
            for term in re.findall(r"\w+", query, flags=re.UNICODE)
            if term.casefold() not in STOP_WORDS and term.casefold() not in {"wasalt", "darglobal"}
        ]
        if not terms and not source_filter:
            return []
        fetch_limit = limit * 10
        if terms:
            where_clauses = ["documents MATCH ?"]
            parameters: list[str | int] = [" OR ".join(f'"{term}"' for term in terms)]
            if source_filter:
                where_clauses.append("source = ?")
                parameters.append(source_filter)
            parameters.append(fetch_limit)
            query_sql = f"""
                SELECT title, content, url, source
                FROM documents
                WHERE {' AND '.join(where_clauses)}
                ORDER BY bm25(documents)
                LIMIT ?
            """
        else:
            query_sql = """
                SELECT title, content, url, source
                FROM documents
                WHERE source = ?
                ORDER BY
                    CASE WHEN url LIKE '%/property/%' OR url LIKE '%/sale/%' OR url LIKE '%/rent/%'
                    THEN 1 ELSE 0 END,
                    length(content) DESC
                LIMIT ?
            """
            parameters = [source_filter, fetch_limit]
        with self._connect() as connection:
            rows = connection.execute(query_sql, tuple(parameters)).fetchall()
        results = []
        seen_urls = set()
        for row in rows:
            if row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(dict(row))
            if len(results) >= limit:
                break
        return results
