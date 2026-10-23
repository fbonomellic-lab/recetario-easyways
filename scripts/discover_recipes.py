#!/usr/bin/env python3
"""Discover recipe URLs from official EasyWays catalog pages.

Only public metadata (title, URL, source country, machine, first-seen date).
Never infer ingredients, oven use, duration or instructions.
Fails safely: network errors do not erase the existing catalog.
"""
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "discovered_recipes.json"
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()
SOURCES = [
    ("CL", "https://easyways.cl/blogs/recetas/tagged/kitchen-pro?page={page}", 15),
    ("AR", "https://recetas.easyways.com.ar/kitchen-pro/", 1),
]
ALLOWED = {"easyways.cl", "www.easyways.cl", "recetas.easyways.com.ar"}

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.text = []
    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(self.text).strip()))
            self.href = None
            self.text = []

def get(url):
    req = Request(url, headers={"User-Agent": "EasyWaysPersonalRecipeIndex/0.1 (public catalog metadata)", "Accept": "text/html"})
    with urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read(3_000_000).decode("utf-8", errors="replace")

def canonical(base, href, country):
    url = urljoin(base, href).split("#")[0].split("?")[0].rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED:
        return None
    if country == "CL" and not re.fullmatch(r"/blogs/recetas/[a-z0-9][a-z0-9-]*", parsed.path):
        return None
    if country == "AR" and not re.fullmatch(r"/kitchen-pro/[a-z0-9][a-z0-9-]*", parsed.path):
        return None
    return url

def discover(country, url):
    page = Links()
    page.feed(get(url))
    found = {}
    for href, title in page.links:
        link = canonical(url, href, country)
        if not link:
            continue
        slug = unquote(urlparse(link).path.rsplit("/", 1)[-1])
        label = html.unescape(title).strip()
        # A slug-based title is only a fallback label, not a verified recipe title.
        if not label or len(label) > 140:
            label = slug.replace("-", " ").capitalize()
        found[link] = {"id": country.lower() + ":" + slug, "title": label,
                       "country": country, "machine": "Kitchen Pro",
                       "source_url": link, "first_seen": TODAY}
    return found

def main():
    old = json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else []
    indexed = {x["source_url"]: x for x in old}
    successes = 0
    for country, pattern, max_pages in SOURCES:
        for page in range(1, max_pages + 1):
            url = pattern.format(page=page)
            try:
                found = discover(country, url)
            except Exception as exc:
                print(f"WARNING {country} page {page}: {exc}", file=sys.stderr)
                break
            if not found:
                print(f"INFO no matching links: {url}")
                break
            successes += 1
            before = len(indexed)
            for link, item in found.items():
                if link not in indexed:
                    indexed[link] = item
            print(f"{country} page {page}: {len(found)} links; +{len(indexed)-before} new")
            if country == "AR":
                break
    if successes == 0:
        print("ERROR no catalogs could be fetched; keeping existing data", file=sys.stderr)
        return 1
    DEST.parent.mkdir(parents=True, exist_ok=True)
    result = sorted(indexed.values(), key=lambda x: (x["country"], x["source_url"]))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if not DEST.exists() or DEST.read_text(encoding="utf-8") != rendered:
        DEST.write_text(rendered, encoding="utf-8")
    print(f"Total discovered: {len(result)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
