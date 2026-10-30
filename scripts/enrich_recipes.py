#!/usr/bin/env python3
"""Conservatively enrich discovered EasyWays recipe links from JSON-LD Recipe data.

Only use Recipe structured data published by the original page. No guessing.
This file intentionally does not copy full recipe instructions.
"""
import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/discovered_recipes.json"
DEST = ROOT / "data/enriched_recipes.json"
ALIASES = ROOT / "data/ingredient_aliases.json"
MAX_PER_RUN = 24

class JSONLD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []
        self.blocks = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self.inside = True
            self.parts = []
    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.inside:
            self.blocks.append("".join(self.parts))
            self.inside = False

def recipes_in(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from recipes_in(x)
    elif isinstance(obj, dict):
        kind = obj.get("@type", [])
        if isinstance(kind, str):
            kind = [kind]
        if "Recipe" in kind:
            yield obj
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in obj:
                yield from recipes_in(obj[key])

def normalize_ingredient(raw, aliases):
    raw = html.unescape(re.sub(r"<[^>]*>", " ", str(raw)))
    raw = re.sub(r"\s+", " ", raw).strip()
    # Do not infer an ingredient from quantities or recipe instructions.
    # Retain the original line; only replace exact recognized ingredient names.
    return aliases.get(raw.casefold(), raw)

def fetch(url):
    req = Request(url, headers={"User-Agent": "EasyWaysPersonalRecipeIndex/0.2 (public structured recipe metadata)", "Accept": "text/html"})
    with urlopen(req, timeout=18) as response:
        return response.read(2_500_000).decode("utf-8", errors="replace")


class VisibleIngredients(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignore = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self.ignore += 1
        if not self.ignore and tag in ("h1", "h2", "h3", "h4", "li", "p", "br"):
            self.parts.append(chr(10))
    def handle_endtag(self, tag):
        if not self.ignore and tag in ("h1", "h2", "h3", "h4", "li", "p"):
            self.parts.append(chr(10))
        if tag in ("script", "style", "nav", "footer") and self.ignore:
            self.ignore -= 1
    def handle_data(self, data):
        if not self.ignore:
            self.parts.append(data)

def visible_ingredients(document):
    parser = VisibleIngredients()
    parser.feed(document)
    lines = [re.sub(r"\s+", " ", html.unescape(x)).strip(" –-•\t") for x in "".join(parser.parts).splitlines()]
    begin = next((i for i, x in enumerate(lines) if re.fullmatch(r"(?i)ingredientes(?: para (?:la masa|el relleno|la cobertura))?", x)), None)
    if begin is None:
        return []
    output = []
    for x in lines[begin + 1:]:
        if re.match(r"(?i)^(instrucciones de preparación|preparación|preparacion|notas?|comentarios)\b", x):
            break
        if not x or len(x) > 150 or re.match(r"(?i)^ingredientes para", x):
            continue
        if re.match(r"(?i)^(\d+(?:[.,/]\d+)?\s*(?:g|gr|kg|ml|l|unidades?|tazas?|cucharadas?|cucharaditas?|pizcas?|rebanadas?|ramas?)\b|\d+\s|sal$|pimienta$|aceite$|perejil$|cilantro$|queso rallado)", x):
            output.append(x)
    return output if 2 <= len(output) <= 65 else []

def main():
    discovered = json.loads(SOURCE.read_text(encoding="utf-8"))
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    old = json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else []
    saved = {x["source_url"]: x for x in old}
    attempted = 0
    added = 0
    no_recipe_data = 0
    fetch_errors = 0
    # Sample both countries instead of spending the whole run on AR entries.
    countries = ("CL", "AR")
    batches = [[x for x in discovered if x["country"] == country and x["source_url"] not in saved][:MAX_PER_RUN // 2] for country in countries]
    for item in [x for batch in batches for x in batch]:
        url = item["source_url"]
        attempted += 1
        try:
            parser = JSONLD()
            document = fetch(url)
            parser.feed(document)
            candidate = None
            for block in parser.blocks:
                try:
                    for recipe in recipes_in(json.loads(block)):
                        if recipe.get("recipeIngredient"):
                            candidate = recipe
                            break
                except (ValueError, TypeError):
                    continue
                if candidate:
                    break
            visible = visible_ingredients(document) if not candidate else []
            if not candidate and not visible:
                if no_recipe_data < 4:
                    plain = VisibleIngredients()
                    plain.feed(document)
                    raw = "".join(plain.parts)
                    match = re.search("ingredientes", raw, re.IGNORECASE)
                    snippet = raw[max(0, match.start()-120):match.start()+900] if match else raw[:350]
                    print(f"DIAGNOSTIC country={item['country']} url={url} html_bytes={len(document)} contains_ingredientes={bool(match)} sample={snippet[:900]!r}")
                no_recipe_data += 1
                print(f"SKIP no Recipe JSON-LD ingredients: {url}")
                continue
            original = candidate["recipeIngredient"] if candidate else visible
            if not isinstance(original, list) or not all(isinstance(x, str) for x in original):
                continue
            saved[url] = {
                "id": item["id"],
                "title": str(candidate.get("name") if candidate else item["title"]).splitlines()[0].strip(),
                "country": item["country"],
                "source_url": url,
                "machine": None,
                "original_ingredients": original,
                "ingredients_display": [normalize_ingredient(x, aliases) for x in original],
                "extraction_method": "jsonld" if candidate else "visible",
                "ingredient_filter_ready": False,
                "first_seen": item["first_seen"],
                "enriched_on": dt.datetime.now(dt.timezone.utc).date().isoformat(),
            }
            added += 1
            print(f"ADDED {url}")
        except Exception as exc:
            fetch_errors += 1
            print(f"WARNING {url}: {exc}", file=sys.stderr)
    output = json.dumps(sorted(saved.values(), key=lambda x: x["source_url"]), ensure_ascii=False, indent=2) + chr(10)
    if not DEST.exists() or DEST.read_text(encoding="utf-8") != output:
        DEST.write_text(output, encoding="utf-8")
    print(f"SUMMARY checked={attempted} added={added} no_structured_ingredients={no_recipe_data} fetch_errors={fetch_errors} total={len(saved)}")
    if added == 0:
        print("NOTICE No ingredient data extracted. Check whether sites expose Recipe JSON-LD; the next extractor will need a site-specific parser.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
