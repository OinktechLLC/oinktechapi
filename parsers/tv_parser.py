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
import socket
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, date, timedelta
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

HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "8"))
TV_LOOKUP_DELAY = float(os.environ.get("TV_LOOKUP_DELAY", "0.2"))
TV_ENABLE_WEB_FALLBACK = os.environ.get("TV_ENABLE_WEB_FALLBACK", "1") != "0"

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
    "five": {"name": "5 канал", "aliases": ["5tv", "пятый", "петербург"]},
    "dozhd": {"name": "Дождь", "aliases": ["tvrain", "rain", "дождь", "dozhd"]},
    "otr": {"name": "ОТР", "aliases": ["otr", "общественное телевидение россии"]},
    "tvc": {"name": "ТВ Центр", "aliases": ["tvc", "твц", "тв центр"]},
    "zvezda": {"name": "Звезда", "aliases": ["zvezda", "звезда"]},
    "mir": {"name": "МИР", "aliases": ["mir", "мир"]},
    "spas": {"name": "Спас", "aliases": ["spas", "спас"]},
    "karusel": {"name": "Карусель", "aliases": ["karusel", "карусель"]},
    "che": {"name": "Че", "aliases": ["che", "че"]},
    "u": {"name": "Ю", "aliases": ["u", "ю", "kanal-u"]},
    "2x2": {"name": "2x2", "aliases": ["2x2", "дважды два"]},
    "super": {"name": "Суббота!", "aliases": ["subbota", "суббота", "super"]},
    "rbc": {"name": "РБК", "aliases": ["rbc", "рбк"]},
    "moscow24": {"name": "Москва 24", "aliases": ["moscow24", "москва24"]},
    "360": {"name": "360°", "aliases": ["360", "360tv"]},
    "redline": {"name": "Красная линия", "aliases": ["redline", "красная линия"]},
}


def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes | None:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    """Пробует получить расписание из JSON API tv.yandex.ru.

    У Яндекса в разных выдачах встречаются channelId, slug и текстовый поиск,
    поэтому перебираем несколько безопасных вариантов и нормально переживаем
    сетевые блокировки/изменение схемы ответа.
    """
    programs: list[dict] = []
    today = date.today().strftime("%Y-%m-%d")
    # Не перебираем все aliases: при сетевых блокировках это превращало запуск в десятки
    # запросов на канал и могло завершать workflow по таймауту.
    names = [channel_id, channel_info.get("name", "")]
    candidates = []

    for name in names:
        if not name:
            continue
        quoted = urllib.parse.quote(str(name))
        candidates.extend([
            f"https://tv.yandex.ru/api/v2/schedule?channelId={quoted}&date={today}&lang=ru",
            f"https://tv.yandex.ru/api/v2/schedule?slug={quoted}&date={today}&lang=ru",
            f"https://tv.yandex.ru/api/v2/search?text={quoted}&date={today}&lang=ru",
        ])

    for url in dict.fromkeys(candidates):
        data = http_get(url, timeout=HTTP_TIMEOUT)
        if not data:
            continue
        try:
            obj = json.loads(data.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError as e:
            log.debug(f"Yandex TV JSON parse error for {channel_id}: {e}")
            continue

        for item in _walk_json(obj):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("name")
            start = item.get("start") or item.get("startTime") or item.get("time")
            if not title or not start:
                continue
            programs.append({
                "title": str(title),
                "start": _normalize_time(start),
                "end": _normalize_time(item.get("end") or item.get("finish") or item.get("endTime") or ""),
                "description": str(item.get("description") or item.get("desc") or "")[:300],
                "genre": str(item.get("genre") or item.get("category") or ""),
                "source": "yandex_tv",
            })

        if programs:
            break

    return programs


def _walk_json(value):
    """Обходит JSON и отдает все вложенные dict/list элементы."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _normalize_time(value) -> str:
    if not value:
        return ""
    text = str(value)
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return text


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
        data = http_get(source_url, timeout=HTTP_TIMEOUT)
        if not data:
            continue
        
        # Распаковка архивов если нужно
        if source_url.endswith(".gz"):
            try:
                import gzip
                data = gzip.decompress(data)
            except Exception as e:
                log.warning(f"gzip decompress failed: {e}")
                continue
        elif source_url.endswith(".zip"):
            try:
                import io
                import zipfile

                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    xml_names = [n for n in archive.namelist() if n.lower().endswith((".xml", ".xmltv"))]
                    if not xml_names:
                        log.info(f"ZIP {source_url} does not contain XMLTV files")
                        continue
                    data = archive.read(xml_names[0])
            except Exception as e:
                log.warning(f"zip unpack failed: {e}")
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


def build_placeholder_schedule(channel_name: str) -> list[dict]:
    """Возвращает безопасную заглушку, если внешние EPG-источники недоступны.

    GitHub Actions/CI нередко получают 403 от EPG и поисковых сервисов. Раньше в
    этом случае файл канала оставался пустым или запуск срывался таймаутом.
    Заглушка сохраняет валидный API-ответ и явно помечает источник как fallback.
    """
    return [
        {
            "title": f"Расписание {channel_name} временно недоступно",
            "start": "00:00",
            "end": "23:59",
            "description": "Внешние источники EPG не ответили. Парсер повторит поиск при следующем запуске.",
            "genre": "service",
            "source": "fallback",
        }
    ]


def build_daily_schedule() -> dict:
    """Собирает полное дневное расписание всех каналов"""
    log.info("=== Building daily TV schedule ===")
    
    # 1. Основной источник — XMLTV
    schedule = fetch_xmltv_epg()
    
    # 2. Дополняем из Яндекс.ТВ JSON API и веб-поиска для недостающих каналов
    for key, info in CHANNEL_REGISTRY.items():
        if key not in schedule or len(schedule[key]) < 5:
            schedule.setdefault(key, [])

            log.info(f"Searching Yandex TV JSON API for channel: {info['name']}")
            yandex_progs = fetch_yandex_tv(key, info)
            if yandex_progs:
                schedule[key].extend(yandex_progs)

            if TV_ENABLE_WEB_FALLBACK and len(schedule[key]) < 5:
                log.info(f"Searching web for channel: {info['name']}")
                web_progs = search_schedule_web(info["name"])
                if web_progs:
                    schedule[key].extend(web_progs)

            if not schedule[key]:
                schedule[key].extend(build_placeholder_schedule(info["name"]))

            time.sleep(TV_LOOKUP_DELAY)  # вежливая пауза
    
    # 3. Обогащаем метаданными
    result = {
        "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
