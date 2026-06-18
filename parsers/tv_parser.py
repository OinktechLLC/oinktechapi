#!/usr/bin/env python3
"""
OinkTech TV Parser — EPG агрегатор расписания телеканалов
Источники: Яндекс.ТВ, XMLTV, поисковые движки
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
from datetime import datetime, date, timedelta
from pathlib import Path
import re
import random

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TV] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("tv_parser")

DATA_DIR = Path(os.environ.get("DATA_DIR", "data/tv"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]

XMLTV_SOURCES = [
    "https://iptvx.one/epg/epg.xml.gz",
    "https://www.teleguide.info/download/new3/jtv.zip",
    "https://epg.it999.ru/edem.xml.gz",
    "https://epg.it999.ru/epg2.xml.gz",
]

# Каналы которые ищем — расширяемый реестр
CHANNEL_REGISTRY = {
    "russia1": {"name": "Россия 1", "aliases": ["russia-1", "р1", "вгтрк"]},
    "perviy": {"name": "Первый канал", "aliases": ["1tv", "otv", "первый"]},
    "ntv": {"name": "НТВ", "aliases": ["ntv", "нтв"]},
    "match": {"name": "Матч ТВ", "aliases": ["matchtv", "матч"]},
    "tnt": {"name": "ТНТ", "aliases": ["tnt"]},
    "sts": {"name": "СТС", "aliases": ["sts", "стс"]},
    "ren": {"name": "РЕН ТВ", "aliases": ["ren", "рен"]},
    "dom2": {"name": "Дом-2", "aliases": []},
    "muz": {"name": "МУЗ-ТВ", "aliases": ["muz", "муз"]},
    "tv3": {"name": "ТВ-3", "aliases": ["tv3", "тв3"]},
    "friday": {"name": "Пятница!", "aliases": ["friday", "пятница"]},
    "tbk": {"name": "ТВК", "aliases": []},
    "culture": {"name": "Культура", "aliases": ["tvkultura", "культура"]},
    "russia24": {"name": "Россия 24", "aliases": ["r24", "р24"]},
    "five": {"name": "5 канал", "aliases": ["5tv", "пятый"]},
}


def http_get(url: str, timeout: int = 20) -> bytes | None:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        log.warning(f"GET {url} -> {e}")
        return None


def fetch_yandex_tv(channel_id: str, channel_info: dict) -> list[dict]:
    """Парсит расписание с tv.yandex.ru через их открытый API"""
    programs = []
    today = date.today().strftime("%Y-%m-%d")
    
    # Яндекс.ТВ API (публичный endpoint)
    url = f"https://tv.yandex.ru/api/v2/schedule?channelId={channel_id}&date={today}&lang=ru"
    data = http_get(url)
    if not data:
        return programs
    
    try:
        obj = json.loads(data.decode("utf-8", errors="ignore"))
        schedule = obj.get("schedules", [])
        for item in schedule:
            programs.append({
                "title": item.get("title", ""),
                "start": item.get("start", ""),
                "end": item.get("end", ""),
                "description": item.get("description", ""),
                "genre": item.get("genre", ""),
                "source": "yandex_tv",
            })
    except Exception as e:
        log.debug(f"Yandex TV parse error: {e}")
    
    return programs


def search_schedule_web(channel_name: str) -> list[dict]:
    """Ищет расписание через DuckDuckGo/Яндекс поиск"""
    programs = []
    today_str = date.today().strftime("%d.%m.%Y")
    query = f"расписание {channel_name} на сегодня {today_str} программа передач"
    
    encoded = urllib.parse.quote(query)
    # DuckDuckGo HTML (не требует JS)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    data = http_get(url)
    if not data:
        return programs
    
    text = data.decode("utf-8", errors="ignore")
    
    # Базовая эвристика — ищем паттерны времени и названий передач
    time_pattern = re.compile(r'(\d{2}:\d{2})\s*[-–—]\s*(.{5,80}?)(?=\d{2}:\d{2}|$)', re.MULTILINE)
    matches = time_pattern.findall(text)
    
    for t, title in matches[:20]:
        title_clean = re.sub(r'<[^>]+>', '', title).strip()
        if len(title_clean) > 3:
            programs.append({
                "title": title_clean,
                "start": t,
                "end": "",
                "description": "",
                "genre": "",
                "source": "web_search",
            })
    
    return programs


def fetch_xmltv_epg() -> dict[str, list[dict]]:
    """Скачивает и парсит XMLTV EPG файл"""
    result: dict[str, list[dict]] = {}
    
    for source_url in XMLTV_SOURCES:
        log.info(f"Trying XMLTV: {source_url}")
        data = http_get(source_url, timeout=30)
        if not data:
            continue
        
        # Распаковка gz если нужно
        if source_url.endswith(".gz"):
            try:
                import gzip
                data = gzip.decompress(data)
            except Exception as e:
                log.warning(f"gzip decompress failed: {e}")
                continue
        
        try:
            root = ET.fromstring(data.decode("utf-8", errors="ignore"))
        except ET.ParseError:
            # Попробуем найти начало XML
            text = data.decode("utf-8", errors="ignore")
            xml_start = text.find("<?xml")
            if xml_start == -1:
                xml_start = text.find("<tv")
            if xml_start == -1:
                continue
            try:
                root = ET.fromstring(text[xml_start:])
            except Exception:
                continue
        
        channels_found = 0
        for programme in root.findall("programme"):
            chan_id = programme.get("channel", "").lower()
            start_raw = programme.get("start", "")
            stop_raw = programme.get("stop", "")
            
            title_el = programme.find("title")
            desc_el = programme.find("desc")
            cat_el = programme.find("category")
            
            title = title_el.text if title_el is not None else ""
            desc = desc_el.text if desc_el is not None else ""
            genre = cat_el.text if cat_el is not None else ""
            
            if not title:
                continue
            
            # Ищем совпадение с нашим реестром каналов
            matched_key = None
            for key, info in CHANNEL_REGISTRY.items():
                check_names = [key, info["name"].lower()] + [a.lower() for a in info.get("aliases", [])]
                if any(n in chan_id for n in check_names):
                    matched_key = key
                    break
            
            if not matched_key:
                # Авторасширение реестра — добавляем неизвестные каналы
                matched_key = chan_id.split(".")[0][:20]
            
            if matched_key not in result:
                result[matched_key] = []
            
            result[matched_key].append({
                "title": title,
                "start": _parse_xmltv_time(start_raw),
                "end": _parse_xmltv_time(stop_raw),
                "description": desc[:300] if desc else "",
                "genre": genre,
                "source": "xmltv",
            })
            channels_found += 1
        
        log.info(f"XMLTV {source_url} — parsed {channels_found} entries, {len(result)} channels")
        
        if channels_found > 100:
            break  # Достаточно одного хорошего источника
    
    return result


def _parse_xmltv_time(raw: str) -> str:
    """20240618143000 +0300 -> 14:30"""
    if not raw:
        return ""
    try:
        dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S")
        return dt.strftime("%H:%M")
    except Exception:
        return raw[:5] if len(raw) >= 5 else raw


def build_daily_schedule() -> dict:
    """Собирает полное дневное расписание всех каналов"""
    log.info("=== Building daily TV schedule ===")
    
    # 1. Основной источник — XMLTV
    schedule = fetch_xmltv_epg()
    
    # 2. Дополняем из Яндекс.ТВ и веб-поиска для недостающих каналов
    for key, info in CHANNEL_REGISTRY.items():
        if key not in schedule or len(schedule[key]) < 5:
            log.info(f"Searching web for channel: {info['name']}")
            web_progs = search_schedule_web(info["name"])
            if web_progs:
                if key not in schedule:
                    schedule[key] = []
                schedule[key].extend(web_progs)
            time.sleep(1)  # вежливая пауза
    
    # 3. Обогащаем метаданными
    result = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "date": date.today().isoformat(),
        "channels": {},
    }
    
    for key, programs in schedule.items():
        channel_info = CHANNEL_REGISTRY.get(key, {"name": key, "aliases": []})
        # Сортируем по времени начала
        programs_sorted = sorted(programs, key=lambda x: x.get("start", ""))
        # Дедупликация по title+start
        seen = set()
        deduped = []
        for p in programs_sorted:
            k = f"{p['title']}|{p['start']}"
            if k not in seen:
                seen.add(k)
                deduped.append(p)
        
        result["channels"][key] = {
            "id": key,
            "name": channel_info.get("name", key),
            "programs": deduped,
            "programs_count": len(deduped),
        }
    
    log.info(f"Schedule ready: {len(result['channels'])} channels")
    return result


def save_schedule(schedule: dict):
    today = date.today().isoformat()
    
    # Полный файл
    full_path = DATA_DIR / f"schedule_{today}.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    
    # Актуальный (latest) — симлинк-заглушка
    latest_path = DATA_DIR / "schedule_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    
    # По каналам отдельно
    channels_dir = DATA_DIR / "channels"
    channels_dir.mkdir(exist_ok=True)
    for ch_id, ch_data in schedule["channels"].items():
        ch_path = channels_dir / f"{ch_id}.json"
        with open(ch_path, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": schedule["updated_at"],
                "date": schedule["date"],
                **ch_data
            }, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved: {full_path} + {len(schedule['channels'])} channel files")


def generate_api_index(schedule: dict):
    """Генерирует api/index.json — список всех доступных каналов"""
    index = {
        "updated_at": schedule["updated_at"],
        "date": schedule["date"],
        "channels": [
            {
                "id": k,
                "name": v["name"],
                "programs_count": v["programs_count"],
                "url": f"channels/{k}.json",
            }
            for k, v in schedule["channels"].items()
        ],
        "total_channels": len(schedule["channels"]),
    }
    idx_path = DATA_DIR / "index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    log.info(f"API index: {idx_path}")


if __name__ == "__main__":
    schedule = build_daily_schedule()
    save_schedule(schedule)
    generate_api_index(schedule)
    log.info("Done.")
