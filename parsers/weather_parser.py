#!/usr/bin/env python3
"""
OinkTech Weather Parser — погода по городам России
Источник: Open-Meteo (бесплатный, без ключа)
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WEATHER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("weather_parser")

DATA_DIR = Path(os.environ.get("DATA_DIR", "data/weather"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Топ городов России
CITIES = {
    "moscow": {"name": "Москва", "lat": 55.7558, "lon": 37.6176, "tz": "Europe/Moscow"},
    "spb": {"name": "Санкт-Петербург", "lat": 59.9311, "lon": 30.3609, "tz": "Europe/Moscow"},
    "novosibirsk": {"name": "Новосибирск", "lat": 54.9885, "lon": 82.9207, "tz": "Asia/Novosibirsk"},
    "ekaterinburg": {"name": "Екатеринбург", "lat": 56.8519, "lon": 60.6122, "tz": "Asia/Yekaterinburg"},
    "kazan": {"name": "Казань", "lat": 55.8304, "lon": 49.0661, "tz": "Europe/Moscow"},
    "nizhny_novgorod": {"name": "Нижний Новгород", "lat": 56.3287, "lon": 44.0020, "tz": "Europe/Moscow"},
    "chelyabinsk": {"name": "Челябинск", "lat": 55.1644, "lon": 61.4368, "tz": "Asia/Yekaterinburg"},
    "samara": {"name": "Самара", "lat": 53.1959, "lon": 50.1002, "tz": "Europe/Samara"},
    "omsk": {"name": "Омск", "lat": 54.9885, "lon": 73.3242, "tz": "Asia/Omsk"},
    "rostov": {"name": "Ростов-на-Дону", "lat": 47.2357, "lon": 39.7015, "tz": "Europe/Moscow"},
    "ufa": {"name": "Уфа", "lat": 54.7388, "lon": 55.9721, "tz": "Asia/Yekaterinburg"},
    "krasnodar": {"name": "Краснодар", "lat": 45.0355, "lon": 38.9753, "tz": "Europe/Moscow"},
    "krasnoyarsk": {"name": "Красноярск", "lat": 56.0153, "lon": 92.8932, "tz": "Asia/Krasnoyarsk"},
    "perm": {"name": "Пермь", "lat": 58.0105, "lon": 56.2502, "tz": "Asia/Yekaterinburg"},
    "voronezh": {"name": "Воронеж", "lat": 51.6655, "lon": 39.2005, "tz": "Europe/Moscow"},
    "volgograd": {"name": "Волгоград", "lat": 48.7080, "lon": 44.5133, "tz": "Europe/Moscow"},
    "saratov": {"name": "Саратов", "lat": 51.5330, "lon": 46.0342, "tz": "Europe/Moscow"},
    "tyumen": {"name": "Тюмень", "lat": 57.1522, "lon": 68.0000, "tz": "Asia/Yekaterinburg"},
    "tolyatti": {"name": "Тольятти", "lat": 53.5111, "lon": 49.4218, "tz": "Europe/Samara"},
    "izhevsk": {"name": "Ижевск", "lat": 56.8527, "lon": 53.2114, "tz": "Europe/Samara"},
}

WMO_CODES = {
    0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
    45: "Туман", 48: "Иней", 51: "Лёгкая морось", 53: "Морось", 55: "Сильная морось",
    61: "Небольшой дождь", 63: "Дождь", 65: "Сильный дождь",
    71: "Небольшой снег", 73: "Снег", 75: "Сильный снег",
    77: "Снежная крупа", 80: "Ливень", 81: "Сильный ливень", 82: "Очень сильный ливень",
    85: "Снегопад", 86: "Сильный снегопад", 95: "Гроза", 96: "Гроза с градом", 99: "Сильная гроза с градом",
}

WIND_DIRECTIONS = ["С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ", "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"]


def http_get(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "OinkTech-Weather/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception as e:
        log.warning(f"GET {url} -> {e}")
        return None


def wind_direction(degrees: float) -> str:
    idx = round(degrees / 22.5) % 16
    return WIND_DIRECTIONS[idx]


def fetch_city_weather(city_key: str, city: dict) -> dict | None:
    params = urllib.parse.urlencode({
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,wind_speed_10m_max",
        "timezone": city["tz"],
        "forecast_days": 7,
        "wind_speed_unit": "ms",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    data = http_get(url)
    if not data:
        return None
    
    try:
        obj = json.loads(data)
        cur = obj.get("current", {})
        daily = obj.get("daily", {})
        hourly = obj.get("hourly", {})
        
        # Прогноз на 7 дней
        forecast = []
        days_count = len(daily.get("time", []))
        for i in range(days_count):
            wc = daily.get("weather_code", [0])[i] if i < len(daily.get("weather_code", [])) else 0
            forecast.append({
                "date": daily["time"][i] if i < len(daily.get("time", [])) else "",
                "temp_max": round(daily.get("temperature_2m_max", [0])[i], 1) if i < len(daily.get("temperature_2m_max", [])) else 0,
                "temp_min": round(daily.get("temperature_2m_min", [0])[i], 1) if i < len(daily.get("temperature_2m_min", [])) else 0,
                "precipitation_mm": round(daily.get("precipitation_sum", [0])[i], 1) if i < len(daily.get("precipitation_sum", [])) else 0,
                "wind_max_ms": round(daily.get("wind_speed_10m_max", [0])[i], 1) if i < len(daily.get("wind_speed_10m_max", [])) else 0,
                "weather_code": wc,
                "description": WMO_CODES.get(wc, "Неизвестно"),
            })
        
        # Почасовой прогноз (ближайшие 24 ч)
        hourly_data = []
        for i in range(min(24, len(hourly.get("time", [])))):
            hourly_data.append({
                "time": hourly["time"][i],
                "temp": round(hourly.get("temperature_2m", [0])[i], 1),
                "precip_prob": hourly.get("precipitation_probability", [0])[i] if i < len(hourly.get("precipitation_probability", [])) else 0,
                "weather_code": hourly.get("weather_code", [0])[i] if i < len(hourly.get("weather_code", [])) else 0,
            })
        
        wc_cur = cur.get("weather_code", 0)
        wd = cur.get("wind_direction_10m", 0)
        
        return {
            "city_key": city_key,
            "city_name": city["name"],
            "latitude": city["lat"],
            "longitude": city["lon"],
            "timezone": city["tz"],
            "current": {
                "temperature": round(cur.get("temperature_2m", 0), 1),
                "feels_like": round(cur.get("apparent_temperature", 0), 1),
                "humidity": cur.get("relative_humidity_2m", 0),
                "precipitation_mm": cur.get("precipitation", 0),
                "pressure_hpa": round(cur.get("pressure_msl", 1013), 0),
                "wind_speed_ms": round(cur.get("wind_speed_10m", 0), 1),
                "wind_direction_deg": wd,
                "wind_direction_text": wind_direction(wd),
                "weather_code": wc_cur,
                "description": WMO_CODES.get(wc_cur, "Неизвестно"),
            },
            "hourly": hourly_data,
            "forecast_7d": forecast,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.warning(f"Parse weather {city_key}: {e}")
        return None


def fetch_all_weather() -> dict:
    log.info("=== Fetching weather for all cities ===")
    cities_data = {}
    
    for key, city in CITIES.items():
        log.info(f"  {city['name']}...")
        w = fetch_city_weather(key, city)
        if w:
            cities_data[key] = w
    
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cities_count": len(cities_data),
        "cities": cities_data,
    }
    log.info(f"Weather fetched for {len(cities_data)} cities")
    return result


def save_weather(data: dict):
    latest_path = DATA_DIR / "weather_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    cities_dir = DATA_DIR / "cities"
    cities_dir.mkdir(exist_ok=True)
    for key, city_data in data["cities"].items():
        with open(cities_dir / f"{key}.json", "w", encoding="utf-8") as f:
            json.dump(city_data, f, ensure_ascii=False, indent=2)
    
    # Index
    index = {
        "updated_at": data["updated_at"],
        "cities": [
            {
                "key": k,
                "name": v["city_name"],
                "temp": v["current"]["temperature"],
                "description": v["current"]["description"],
                "url": f"cities/{k}.json",
            }
            for k, v in data["cities"].items()
        ],
    }
    with open(DATA_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    log.info(f"Saved weather to {DATA_DIR}")


if __name__ == "__main__":
    weather = fetch_all_weather()
    save_weather(weather)
    log.info("Done.")
