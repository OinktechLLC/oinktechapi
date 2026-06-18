# 🐷 OinkTech API — Агрегация Цифровых Функций

> Бесплатные API для разработчиков: ТВ-расписание, новости, погода, курсы валют.  
> Автоматическое обновление через GitHub Actions. Никаких ключей, серверов или регистрации.

[![TV Parser](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/tv_parser.yml/badge.svg)](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/tv_parser.yml)
[![News Parser](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/news_parser.yml/badge.svg)](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/news_parser.yml)
[![Weather & Rates](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/weather_rates.yml/badge.svg)](https://github.com/YOUR_ORG/oinktech-api/actions/workflows/weather_rates.yml)

---

## 🚀 Быстрый старт

```js
const BASE = "https://raw.githubusercontent.com/YOUR_ORG/oinktech-api/main/data";

// ТВ-расписание — все каналы
const tv = await fetch(`${BASE}/tv/schedule_latest.json`).then(r => r.json());

// Погода в Москве
const weather = await fetch(`${BASE}/weather/cities/moscow.json`).then(r => r.json());
console.log(weather.current.temperature); // → -3.5

// Курс USD/RUB
const rates = await fetch(`${BASE}/rates/rates_latest.json`).then(r => r.json());
console.log(rates.highlight.USD); // → 89.34

// Новости (общие)
const news = await fetch(`${BASE}/news/categories/general.json`).then(r => r.json());
```

---

## 📦 Структура проекта

```
oinktech-api/
├── parsers/
│   ├── tv_parser.py          # ТВ-расписание (XMLTV + Яндекс.ТВ + веб-поиск)
│   ├── news_parser.py        # Новости из 10 RSS-источников
│   ├── weather_parser.py     # Погода для 20 городов (Open-Meteo)
│   └── rates_parser.py       # Курсы ЦБ РФ + криптовалюты (CoinGecko)
├── .github/workflows/
│   ├── tv_parser.yml         # Каждые 3 часа
│   ├── news_parser.yml       # Каждые 6 часов
│   └── weather_rates.yml     # Каждый час
├── data/
│   ├── tv/
│   │   ├── schedule_latest.json
│   │   ├── schedule_YYYY-MM-DD.json
│   │   ├── index.json
│   │   └── channels/
│   │       ├── ntv.json
│   │       ├── russia1.json
│   │       └── ...
│   ├── news/
│   │   ├── news_latest.json
│   │   └── categories/
│   │       ├── general.json
│   │       ├── tech.json
│   │       ├── sport.json
│   │       └── business.json
│   ├── weather/
│   │   ├── weather_latest.json
│   │   ├── index.json
│   │   └── cities/
│   │       ├── moscow.json
│   │       ├── spb.json
│   │       └── ...
│   ├── rates/
│   │   └── rates_latest.json
│   └── meta.json             # Сводный мета-файл всех API
├── landing/
│   └── index.html            # Лендинг с документацией и FAQ
└── requirements.txt
```

---

## 📺 TV Schedule API

### Источники данных
- **XMLTV агрегаторы** — iptvx.one, it999.ru (основной источник)
- **Яндекс.ТВ API** — `tv.yandex.ru` (дополнительный)
- **DuckDuckGo Web Search** — резервный поиск для недостающих каналов

### Поддерживаемые каналы
| ID | Название |
|---|---|
| `russia1` | Россия 1 |
| `perviy` | Первый канал |
| `ntv` | НТВ |
| `match` | Матч ТВ |
| `tnt` | ТНТ |
| `sts` | СТС |
| `ren` | РЕН ТВ |
| `tv3` | ТВ-3 |
| `friday` | Пятница! |
| `culture` | Культура |
| `russia24` | Россия 24 |
| `five` | 5 канал |
| `muz` | МУЗ-ТВ |

### Добавить свой канал

```python
# parsers/tv_parser.py → CHANNEL_REGISTRY
CHANNEL_REGISTRY = {
    "my_channel": {
        "name": "Мой Канал",
        "aliases": ["mychan", "мойканал"]
    },
    # ...
}
```

### Эндпоинты TV

| Путь | Описание |
|---|---|
| `data/tv/schedule_latest.json` | Расписание всех каналов сегодня |
| `data/tv/schedule_YYYY-MM-DD.json` | За конкретную дату |
| `data/tv/channels/{id}.json` | Один канал |
| `data/tv/index.json` | Список каналов |

### Формат ответа

```json
{
  "id": "ntv",
  "name": "НТВ",
  "date": "2025-06-18",
  "updated_at": "2025-06-18T09:00:00Z",
  "programs_count": 24,
  "programs": [
    {
      "title": "Утро. Самое лучшее",
      "start": "08:00",
      "end": "10:00",
      "description": "...",
      "genre": "Информация",
      "source": "xmltv"
    }
  ]
}
```

---

## 📰 News API

### Источники (10 штук)
| Ключ | Источник | Категория |
|---|---|---|
| `ria` | РИА Новости | general |
| `tass` | ТАСС | general |
| `lenta` | Lenta.ru | general |
| `interfax` | Интерфакс | general |
| `kommersant` | Коммерсантъ | business |
| `rbc` | РБК | business |
| `sport_express` | Спорт-Экспресс | sport |
| `championat` | Чемпионат.com | sport |
| `tech_habr` | Хабр | tech |
| `vc` | VC.ru | tech |

### Эндпоинты News

| Путь | Описание |
|---|---|
| `data/news/news_latest.json` | Все (до 200 статей) |
| `data/news/categories/general.json` | Общие |
| `data/news/categories/tech.json` | Технологии |
| `data/news/categories/sport.json` | Спорт |
| `data/news/categories/business.json` | Бизнес |

### Формат статьи

```json
{
  "id": "a1b2c3d4e5f6",
  "title": "Заголовок новости",
  "url": "https://ria.ru/...",
  "description": "Краткое описание...",
  "published_at": "2025-06-18T09:30:00+03:00",
  "source_key": "ria",
  "source_name": "РИА Новости",
  "category": "general"
}
```

---

## 🌤 Weather API

20 городов России. Источник: [Open-Meteo](https://open-meteo.com/) (бесплатный, без ключа).

### Города
`moscow`, `spb`, `novosibirsk`, `ekaterinburg`, `kazan`, `nizhny_novgorod`,
`chelyabinsk`, `samara`, `omsk`, `rostov`, `ufa`, `krasnodar`, `krasnoyarsk`,
`perm`, `voronezh`, `volgograd`, `saratov`, `tyumen`, `tolyatti`, `izhevsk`

### Формат ответа

```json
{
  "city_name": "Москва",
  "current": {
    "temperature": -3.5,
    "feels_like": -8.2,
    "humidity": 78,
    "wind_speed_ms": 4.2,
    "wind_direction_text": "СЗ",
    "pressure_hpa": 1015,
    "description": "Переменная облачность"
  },
  "hourly": [...],
  "forecast_7d": [
    {
      "date": "2025-06-18",
      "temp_max": 2.1,
      "temp_min": -5.3,
      "precipitation_mm": 0.0,
      "description": "Ясно"
    }
  ]
}
```

---

## 💱 Rates API

### Источники
- **ЦБ РФ** — официальный XML (`cbr.ru/scripts/XML_daily.asp`) — 40+ валют
- **CoinGecko** — бесплатный API без ключа — BTC, ETH, TON, SOL, XRP, DOGE, BNB

### Формат ответа

```json
{
  "updated_at": "2025-06-18T10:15:00Z",
  "base_currency": "RUB",
  "highlight": {
    "USD": 89.34,
    "EUR": 97.12,
    "CNY": 12.45,
    "BTC_USD": 67420.5,
    "TON_USD": 7.23
  },
  "fiat": {
    "USD": { "code": "USD", "name": "Доллар США", "rate_rub": 89.34 }
  },
  "crypto": {
    "bitcoin": { "price_usd": 67420.5, "price_rub": 6029833, "change_24h": 2.34 }
  }
}
```

---

## ⚙️ Деплой и настройка

### Шаг 1: Fork

```bash
gh repo fork YOUR_ORG/oinktech-api
cd oinktech-api
```

### Шаг 2: Разреши Actions

Перейди в `Settings → Actions → General → Allow all actions`.

### Шаг 3: Первый запуск вручную

```bash
# Actions → TV Schedule Parser → Run workflow
```

### Шаг 4 (опционально): GitHub Pages для лендинга

```
Settings → Pages → Source: Deploy from branch → main / landing/
```

### Локальный запуск

```bash
pip install -r requirements.txt

# ТВ
DATA_DIR=data/tv python parsers/tv_parser.py

# Новости
DATA_DIR=data/news python parsers/news_parser.py

# Погода
DATA_DIR=data/weather python parsers/weather_parser.py

# Курсы
DATA_DIR=data/rates python parsers/rates_parser.py
```

---

## 🔧 Расписание GitHub Actions

| Воркфлоу | Расписание | Что делает |
|---|---|---|
| `tv_parser.yml` | каждые 3 ч | Парсит XMLTV, Яндекс.ТВ, веб-поиск |
| `news_parser.yml` | каждые 6 ч | Парсит 10 RSS-источников |
| `weather_rates.yml` | каждый час | Погода (Open-Meteo) + курсы (ЦБ + CoinGecko) |

---

## 🤝 Вклад в проект

1. Fork → branch → изменения
2. Тест: `python parsers/tv_parser.py`
3. Pull Request с описанием

---

## 📄 Лицензия

MIT © 2025 OinkTech Ltd / TOO Oink Tech Ltd Co.

Данные принадлежат их владельцам: РИА Новости, ТАСС, Lenta.ru, ЦБ РФ и другим источникам.
