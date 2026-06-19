#!/usr/bin/env python3
"""
OinkTech News Parser — агрегатор новостей из RSS/API
Источники: RIA, TASS, Lenta, RT, Interfax и поисковики
"""

import os
import json
import time
import logging
import hashlib
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
import re
import random

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [NEWS] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("news_parser")

DATA_DIR = Path(os.environ.get("DATA_DIR", "data/news"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/125.0",
]

# RSS источники
RSS_SOURCES = {
    "ria": {
        "name": "РИА Новости",
        "url": "https://ria.ru/export/rss2/archive/index.xml",
        "category": "general",
        "logo": "https://ria.ru/favicon.ico",
    },
    "tass": {
        "name": "ТАСС",
        "url": "https://tass.ru/rss/v2.xml",
        "category": "general",
        "logo": "https://tass.ru/favicon.ico",
    },
    "lenta": {
        "name": "Lenta.ru",
        "url": "https://lenta.ru/rss/news",
        "category": "general",
        "logo": "https://lenta.ru/favicon.ico",
    },
    "kommersant": {
        "name": "Коммерсантъ",
        "url": "https://www.kommersant.ru/RSS/main.xml",
        "category": "business",
        "logo": "https://www.kommersant.ru/favicon.ico",
    },
    "rbc": {
        "name": "РБК",
        "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "category": "business",
        "logo": "https://www.rbc.ru/favicon.ico",
    },
    "sport_express": {
        "name": "Спорт-Экспресс",
        "url": "https://www.sport-express.ru/rss/news/",
        "category": "sport",
        "logo": "https://www.sport-express.ru/favicon.ico",
    },
    "championat": {
        "name": "Чемпионат.com",
        "url": "https://www.championat.com/rss/index.xml",
        "category": "sport",
        "logo": "https://www.championat.com/favicon.ico",
    },
    "tech_habr": {
        "name": "Хабр",
        "url": "https://habr.com/ru/rss/articles/",
        "category": "tech",
        "logo": "https://habr.com/favicon.ico",
    },
    "vc": {
        "name": "VC.ru",
        "url": "https://vc.ru/rss",
        "category": "tech",
        "logo": "https://vc.ru/favicon.ico",
    },
    "interfax": {
        "name": "Интерфакс",
        "url": "https://www.interfax.ru/rss.asp",
        "category": "general",
        "logo": "https://www.interfax.ru/favicon.ico",
    },
}

CATEGORIES = ["general", "business", "tech", "sport", "culture", "world"]

SEARCH_NEWS_QUERIES = {
    "general": ["главные новости сегодня все сми", "срочные новости сегодня"],
    "world": ["мировые новости сегодня все сми", "международные новости сегодня"],
    "business": ["экономика бизнес новости сегодня все сми", "финансовые новости сегодня"],
    "tech": ["технологии IT новости сегодня все сми", "новости искусственный интеллект сегодня"],
    "sport": ["спорт новости сегодня все сми"],
    "culture": ["культура кино музыка новости сегодня"],
}


def http_get(url: str, timeout: int = 15) -> bytes | None:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Cache-Control": "no-cache",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        log.warning(f"GET {url} -> {e}")
        return None


def parse_rss(source_key: str, source: dict) -> list[dict]:
    """Парсит RSS ленту"""
    articles = []
    data = http_get(source["url"])
    if not data:
        return articles
    
    try:
        text = data.decode("utf-8", errors="ignore")
        # Убираем мусор до начала XML
        xml_start = text.find("<?xml")
        if xml_start == -1:
            xml_start = text.find("<rss")
        if xml_start == -1:
            xml_start = text.find("<feed")
        if xml_start == -1:
            return articles
        text = text[xml_start:]
        
        root = ET.fromstring(text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        # RSS 2.0
        items = root.findall(".//item")
        # Atom
        if not items:
            items = root.findall(".//atom:entry", ns) or root.findall(".//entry")
        
        for item in items[:50]:  # Берём последние 50
            def get_text(tags: list[str]) -> str:
                for tag in tags:
                    el = item.find(tag)
                    if el is not None and el.text:
                        return el.text.strip()
                    # С NS
                    for prefix, uri in [("atom", "http://www.w3.org/2005/Atom"),
                                        ("dc", "http://purl.org/dc/elements/1.1/")]:
                        el = item.find(f"{{{uri}}}{tag.split(':')[-1]}")
                        if el is not None and el.text:
                            return el.text.strip()
                return ""
            
            title = get_text(["title"])
            link = get_text(["link", "guid"])
            pubdate = get_text(["pubDate", "published", "updated", "dc:date"])
            description = get_text(["description", "summary", "content"])
            
            # Чистим HTML из описания
            description = re.sub(r'<[^>]+>', '', description)[:500]
            
            if not title or len(title) < 5:
                continue
            
            # Уникальный ID
            uid = hashlib.md5(f"{source_key}:{link or title}".encode()).hexdigest()[:12]
            
            articles.append({
                "id": uid,
                "title": title,
                "url": link,
                "description": description.strip(),
                "published_at": _normalize_date(pubdate),
                "source_key": source_key,
                "source_name": source["name"],
                "category": source["category"],
                "logo": source.get("logo", ""),
            })
    
    except Exception as e:
        log.warning(f"RSS parse error {source_key}: {e}")
    
    log.info(f"  {source['name']}: {len(articles)} articles")
    return articles


def _normalize_date(raw: str) -> str:
    """Нормализуем разные форматы дат в ISO"""
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.isoformat()
        except ValueError:
            continue
    return raw


def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def _extract_ddg_url(raw: str) -> str:
    raw = _clean_html(raw)
    if "uddg=" in raw:
        parsed = urllib.parse.urlparse(raw)
        params = urllib.parse.parse_qs(parsed.query)
        if params.get("uddg"):
            return urllib.parse.unquote(params["uddg"][0])
    return raw


def _domain_name(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    return host or "Поисковый робот"


def search_trending_news() -> list[dict]:
    """Ищет новости поисковым роботом по всем ключевым категориям СМИ."""
    articles = []

    for category, queries in SEARCH_NEWS_QUERIES.items():
        for query in queries:
            encoded = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            data = http_get(url)
            if not data:
                continue

            text = data.decode("utf-8", errors="ignore")
            title_pattern = re.compile(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL)
            snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</(?:a|div|span)>', re.DOTALL)
            url_pattern = re.compile(r'class="result__url"[^>]*>(.*?)</(?:a|span)>', re.DOTALL)

            titles = title_pattern.findall(text)
            snippets = snippet_pattern.findall(text)
            urls = url_pattern.findall(text)

            for i, title in enumerate(titles[:10]):
                title_clean = _clean_html(title)
                snippet = _clean_html(snippets[i]) if i < len(snippets) else ""
                article_url = _extract_ddg_url(urls[i]) if i < len(urls) else ""

                if len(title_clean) < 10:
                    continue

                source_name = _domain_name(article_url)
                uid = hashlib.md5(f"search:{article_url or title_clean}".encode()).hexdigest()[:12]
                articles.append({
                    "id": uid,
                    "title": title_clean,
                    "url": article_url,
                    "description": snippet[:300],
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "source_key": "search_robot",
                    "source_name": source_name,
                    "category": category,
                    "logo": "",
                })

            time.sleep(0.5)

    return articles


def fetch_all_news() -> dict:
    """Собирает новости из всех источников"""
    log.info("=== Fetching all news ===")
    
    all_articles: list[dict] = []
    
    for key, source in RSS_SOURCES.items():
        log.info(f"Parsing {source['name']}...")
        articles = parse_rss(key, source)
        all_articles.extend(articles)
        time.sleep(0.5)  # Пауза между запросами
    
    # Дополняем поисковыми результатами
    log.info("Searching trending news...")
    trending = search_trending_news()
    all_articles.extend(trending)
    
    # Дедупликация по ID
    seen_ids = set()
    unique = []
    for a in all_articles:
        if a["id"] not in seen_ids:
            seen_ids.add(a["id"])
            unique.append(a)
    
    # Сортировка по дате (новые первые)
    unique.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    
    # Группировка по категориям
    by_category: dict[str, list] = {cat: [] for cat in CATEGORIES}
    for article in unique:
        cat = article.get("category", "general")
        if cat in by_category:
            by_category[cat].append(article)
        else:
            by_category["general"].append(article)
    
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(unique),
        "articles": unique[:200],  # Топ 200
        "by_category": {k: v[:50] for k, v in by_category.items()},
        "sources": [
            {"key": k, "name": v["name"], "category": v["category"]}
            for k, v in RSS_SOURCES.items()
        ],
    }
    
    log.info(f"Total unique articles: {len(unique)}")
    return result


def save_news(news: dict):
    from datetime import date
    today = date.today().isoformat()
    
    # Полный снапшот
    full_path = DATA_DIR / f"news_{today}.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    
    # Latest
    latest_path = DATA_DIR / "news_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    
    # По категориям
    cats_dir = DATA_DIR / "categories"
    cats_dir.mkdir(exist_ok=True)
    for cat, articles in news["by_category"].items():
        cat_path = cats_dir / f"{cat}.json"
        with open(cat_path, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": news["updated_at"],
                "category": cat,
                "articles": articles,
            }, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved news to {full_path}")


if __name__ == "__main__":
    news = fetch_all_news()
    save_news(news)
    log.info("Done.")
