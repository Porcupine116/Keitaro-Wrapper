# Adrobot — Keitaro Wrapper

Приложение для тестового задания Adrobot: создание кампании Keitaro с двумя потоками и редактирование офферов существующих кампаний.

## Стек

- Python 3.11+
- FastAPI + Pydantic 2
- SQLAlchemy 2 + SQLite (локальный журнал операций)
- httpx (Keitaro Admin API)
- HTML + CSS + Vanilla JavaScript

## Запуск на Windows

Открой PowerShell в корне проекта:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

В `backend/.env` укажи адрес API и персональный ключ стенда:

```env
KEITARO_BASE_URL=https://keitaro-for-tests.etolegko.com/admin_api/v1
KEITARO_API_KEY=твой-ключ
KEITARO_API_PREFIX=/admin_api/v1
```

Клиент принимает как полный URL API (`.../admin_api/v1`), так и только origin (`https://keitaro-for-tests.etolegko.com`). Префикс не будет добавлен дважды.

Запуск из папки `backend`:

```powershell
uvicorn app.main:app --reload
```

- Приложение: <http://127.0.0.1:8000>
- Swagger нашего backend: <http://127.0.0.1:8000/docs>

API-ключ используется только backend-сервисом, не передаётся в браузер и не должен попадать в Git. Файл `.env` исключён через `.gitignore`.

## Поддержка учебного стенда

Код ориентирован на контракт стенда из ТЗ. В частности, **не вызываются** неподдерживаемые методы `/stream_filters`, `/streams_actions`, `/stream_types`, `/stream_schemas`.

Для создания потоков используются фиксированные значения из документации стенда:

- страна: фильтр `country`, режим `accept`, `payload` — массив кодов стран;
- Google: `type=regular`, `schema=redirect`, `action_type=http`, `action_payload=https://www.google.com`;
- офферы: `type=default`, `schema=landings`, `offers` — массив `{offer_id, share, state}`.

Справочники загружаются из поддержанных GET-методов:

- `GET /domains`
- `GET /groups?type=campaigns`
- `GET /traffic_sources`
- `GET /offers`
- `GET /campaigns?offset=0&limit=100`

Создание кампании выполняет:

1. `POST /campaigns` с названием, alias, доменом, группой и источником.
2. `POST /streams` — regular Google-поток сразу с URL и GEO-фильтром.
3. `POST /streams` — default-поток с выбранным оффером и долей 100%.
4. `GET /campaigns/{id}/streams` — получение созданных потоков для результата.

Создание состоит из нескольких HTTP-запросов, поэтому оно не атомарно. При частичной ошибке backend вернёт ID уже созданной кампании/потока в деталях ошибки; проверь их в стенде перед повторной попыткой, чтобы не создавать дубликаты.

## Редактор кампаний

Редактор загружает все потоки выбранной кампании через `GET /campaigns/{id}/streams`. Добавление и удаление оффера изменяет только выбранный поток:

- чтение потока: `GET /streams/{id}`;
- проверка оффера: `GET /offers/{id}`;
- изменение набора офферов: `PUT /streams/{id}` с полем `offers`.

Так как `PUT` заменяет состав `offers` целиком, backend сначала получает текущий поток, строит полный новый массив, равномерно пересчитывает доли и отправляет его. Сумма долей равна 100%, например для трёх офферов — `33 / 33 / 34`.

Удаление оффера из потока не удаляет сам оффер из общего каталога.

## Ссылки и журнал

Кнопка «Открыть в Keitaro» использует формат стенда:

`https://keitaro-for-tests.etolegko.com/admin/#!/campaign.editor/{id}`

Стенд отдельно ведёт журнал всех запросов обёртки к Admin API. В приложении также сохраняются локальные записи об успешных операциях создания кампании и редактирования офферов.

## Диагностика

- `GET /api/health` — проверка backend.
- `GET /api/keitaro/info` — адрес трекера без API-ключа.
- `GET /api/references` — справочники и список кампаний из стенда.
- `GET /api/keitaro/metadata` — фиксированные возможности учебного стенда; не делает запросов к отсутствующим metadata-маршрутам.

Перед созданием кампании сначала проверь `/api/references`: должны загрузиться домен, группа FORTESTS, источник FORTESTS и список офферов.

## Тесты

Из папки `backend`:

```powershell
py -m unittest discover -s ..\tests -v
```

## Структура

```text
backend/app/api/routes.py                  # HTTP endpoints приложения
backend/app/services/keitaro_client.py     # HTTP-клиент Admin API
backend/app/services/campaign_service.py   # создание кампаний и редактирование офферов
backend/app/models/audit_log.py            # локальный журнал операций SQLAlchemy
frontend/index.html                        # интерфейс
frontend/static/app.js                     # frontend-логика
frontend/static/styles.css                 # стили
tests/                                     # unit-тесты
```
