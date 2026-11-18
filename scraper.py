import gzip
import re
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


BOT_NAME = "DarWasaltDemoBot"
USER_AGENT = f"{BOT_NAME}/1.0 (public website information demo)"
MAX_PAGES_PER_SITE = 80
MAX_SITEMAPS_PER_SITE = 20
REQUEST_DELAY_SECONDS = 0.5
EXCLUDED_PATH_TERMS = ("privacy", "terms", "cookie", "disclaimer", "legal", "policy")
SITES = {
    "DarGlobal": (
        "https://darglobal.co.uk/robots.txt",
        {"darglobal.co.uk", "www.darglobal.co.uk"},
        {"darglobal.co.uk", "www.darglobal.co.uk"},
    ),
    "Wasalt": (
        "https://wasalt.sa/robots.txt",
        {"wasalt.sa", "www.wasalt.sa"},
        {"wasalt.sa", "www.wasalt.sa", "cdn.wasalt.sa"},
    ),
}


def _get(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response


def _parse_robots(session: requests.Session, robots_url: str) -> urllib.robotparser.RobotFileParser:
    response = _get(session, robots_url)
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser


def _xml_root(content: bytes) -> ET.Element:
    if content.startswith(b"\x1f\x8b"):
        content = gzip.decompress(content)
    return ET.fromstring(content)


def _is_relevant_page_url(url: str) -> bool:
    path = urlparse(url).path.casefold()
    return not any(term in path for term in EXCLUDED_PATH_TERMS)


def _sitemap_urls(
    session: requests.Session,
    robots: urllib.robotparser.RobotFileParser,
    allowed_page_hosts: set[str],
    allowed_sitemap_hosts: set[str],
) -> list[str]:
    page_urls: list[str] = []
    sitemap_queue = list(robots.site_maps() or [])
    visited: set[str] = set()

    while sitemap_queue and len(visited) < MAX_SITEMAPS_PER_SITE and len(page_urls) < MAX_PAGES_PER_SITE:
        sitemap_url = sitemap_queue.pop(0)
        if sitemap_url in visited or urlparse(sitemap_url).hostname not in allowed_sitemap_hosts:
            continue
        visited.add(sitemap_url)
        try:
            root = _xml_root(_get(session, sitemap_url).content)
        except (requests.RequestException, ET.ParseError, OSError):
            continue

        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
                continue
            loc = element.text.strip()
            if root.tag.rsplit("}", 1)[-1] == "sitemapindex":
                if urlparse(loc).hostname in allowed_sitemap_hosts:
                    sitemap_queue.append(loc)
            elif (
                urlparse(loc).hostname in allowed_page_hosts
                and _is_relevant_page_url(loc)
                and robots.can_fetch(USER_AGENT, loc)
            ):
                page_urls.append(loc)
                if len(page_urls) >= MAX_PAGES_PER_SITE:
                    break

    return list(dict.fromkeys(page_urls))


def _page_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        element.decompose()
    title = soup.find("h1") or soup.title
    title_text = title.get_text(" ", strip=True) if title else "Website page"
    content = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return title_text[:300], content[:15000]


def scrape_sites() -> tuple[list[dict[str, str]], list[str]]:
    session = requests.Session()
    pages: list[dict[str, str]] = []
    messages: list[str] = []

    for source, (robots_url, allowed_page_hosts, allowed_sitemap_hosts) in SITES.items():
        try:
            robots = _parse_robots(session, robots_url)
        except requests.RequestException as error:
            messages.append(f"{source}: skipped because robots.txt could not be read ({error}).")
            continue

        urls = _sitemap_urls(session, robots, allowed_page_hosts, allowed_sitemap_hosts)
        if not urls:
            messages.append(f"{source}: no crawlable pages were found in its published sitemaps.")
            continue

        collected = 0
        for url in urls:
            if not robots.can_fetch(USER_AGENT, url):
                continue
            try:
                response = _get(session, url)
                final_url = response.url
                if (
                    urlparse(final_url).hostname not in allowed_page_hosts
                    or not _is_relevant_page_url(final_url)
                ):
                    continue
                title, content = _page_text(response.text)
                if len(content) < 100:
                    continue
                pages.append(
                    {
                        "title": title,
                        "content": content,
                        "url": final_url,
                        "source": source,
                    }
                )
                collected += 1
            except requests.RequestException:
                continue
            finally:
                time.sleep(REQUEST_DELAY_SECONDS)
        messages.append(f"{source}: collected {collected} pages (up to {MAX_PAGES_PER_SITE} per site).")

    return pages, messages
