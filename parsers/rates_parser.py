#!/usr/bin/env python3
"""
OinkTech Rates Parser — курсы валют ЦБ РФ + криптовалюты
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RATES] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rates_parser")

DATA_DIR = Path(os.environ.get("DATA_DIR", "data/rates"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def http_get(url: str, timeout: int = 15) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "OinkTech-Rates/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        log.warning(f"GET {url} -> {e}")
        return None


def fetch_cbr_rates() -> dict:
    """Официальный XML ЦБ РФ"""
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    data = http_get(url)
    rates = {}
    
    if not data:
        return rates
    
    try:
        text = data.decode("windows-1251", errors="replace")
        root = ET.fromstring(text.encode("utf-8", errors="replace"))
        date_attr = root.get("Date", "")
        
        for valute in root.findall("Valute"):
            char_code = valute.findtext("CharCode", "")
            name = valute.findtext("Name", "")
            nominal = valute.findtext("Nominal", "1")
            value = valute.findtext("Value", "0").replace(",", ".")
            
            try:
                rate_rub = float(value) / int(nominal)
            except (ValueError, ZeroDivisionError):
                rate_rub = 0.0
            
            rates[char_code] = {
                "code": char_code,
                "name": name,
                "rate_rub": round(rate_rub, 4),
                "nominal": int(nominal),
                "raw_value": value,
            }
        
        log.info(f"CBR: {len(rates)} currencies, date={date_attr}")
    except Exception as e:
        log.warning(f"CBR parse error: {e}")
    
    return rates


def fetch_crypto_rates() -> dict:
    """CoinGecko публичный API (без ключа)"""
    coins = "bitcoin,ethereum,tether,bnb,solana,ripple,dogecoin,toncoin"
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coins}&vs_currencies=usd,rub&include_24hr_change=true"
    data = http_get(url)
    
    if not data:
        return {}
    
    try:
        obj = json.loads(data)
        result = {}
        name_map = {
            "bitcoin": "Bitcoin", "ethereum": "Ethereum", "tether": "Tether",
            "bnb": "BNB", "solana": "Solana", "ripple": "XRP",
            "dogecoin": "Dogecoin", "toncoin": "TON",
        }
        for coin_id, prices in obj.items():
            result[coin_id] = {
                "id": coin_id,
                "name": name_map.get(coin_id, coin_id),
                "price_usd": prices.get("usd", 0),
                "price_rub": prices.get("rub", 0),
                "change_24h": round(prices.get("usd_24h_change", 0), 2),
            }
        log.info(f"CoinGecko: {len(result)} cryptos")
        return result
    except Exception as e:
        log.warning(f"CoinGecko parse error: {e}")
        return {}


def fetch_all_rates() -> dict:
    log.info("=== Fetching rates ===")
    fiat = fetch_cbr_rates()
    crypto = fetch_crypto_rates()
    
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "base_currency": "RUB",
        "fiat": fiat,
        "crypto": crypto,
        "highlight": {
            "USD": fiat.get("USD", {}).get("rate_rub", 0),
            "EUR": fiat.get("EUR", {}).get("rate_rub", 0),
            "CNY": fiat.get("CNY", {}).get("rate_rub", 0),
            "BTC_USD": crypto.get("bitcoin", {}).get("price_usd", 0),
            "ETH_USD": crypto.get("ethereum", {}).get("price_usd", 0),
            "TON_USD": crypto.get("toncoin", {}).get("price_usd", 0),
        },
    }
    return result


def save_rates(data: dict):
    path = DATA_DIR / "rates_latest.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Saved: {path}")


if __name__ == "__main__":
    rates = fetch_all_rates()
    save_rates(rates)
    log.info("Done.")
