# Aura Platform -- Автономная Экономическая Переговорная Платформа

**Aura** -- микросервисная платформа для AI-агентов, способных автономно искать товары/услуги и вести ценовые переговоры с сервис-провайдерами. Проект построен по метафоре "Hexagonal Hive" (Гексагональный Улей) -- биологически-инспирированная архитектура, где каждый компонент имеет роль в экосистеме.

---

## 1. Ключевые возможности

- **Семантический поиск**: агенты ищут товары через естественный язык (PostgreSQL + pgvector, векторный поиск по эмбеддингам).
- **AI-переговоры**: агенты подают ставки, система через DSPy-обученную ML-модель (или rule-based fallback) принимает решение -- accept / counter / reject / ui_required.
- **Крипто-платежи**: принятые сделки могут блокироваться до on-chain оплаты в Solana (SOL/USDC). Секрет (код бронирования) раскрывается после подтверждения платежа.
- **Ed25519 аутентификация**: агенты подписывают запросы, идентификация через DID (`did:key:...`).

---

## 2. Архитектура -- паттерн ATCG + Membrane

Ядро проекта построено по биологической метафоре **метаболического цикла** клетки:

| Компонент | Роль | Описание |
|-----------|------|----------|
| **A -- Aggregator** | Восприятие | Собирает сигнал (запрос агента) + внутреннее состояние (данные из БД, метрики системы) и формирует `HiveContext` |
| **T -- Transformer** | Мышление | Принимает решение: вызывает DSPy/LLM Reasoning Protein или rule-based стратегию. Возвращает `IntentAction` |
| **C -- Connector** | Действие | Преобразует решение в gRPC-ответ, при необходимости создает крипто-сделку через MarketService |
| **G -- Generator** | Пульс | Публикует бинарные protobuf-события в NATS JetStream (negotiation event, heartbeat, vitals) |
| **M -- Membrane** | Иммунитет | Валидирует входящие сигналы (инъекции, отрицательные ставки) и исходящие решения (floor price guard, DLP-фильтр) |

Оркестрация выполняется в `MetabolicLoop`:

```
Signal -> Membrane(inbound) -> Aggregator -> Transformer -> Membrane(outbound) -> Connector -> Generator
```

---

## 3. Микросервисы

### 3.1 Core Service (gRPC, порт 50051)

Главный сервис с бизнес-логикой. Реализует `NegotiationService` с методами:
- `Negotiate` -- основной цикл переговоров
- `Search` -- семантический поиск по pgvector
- `GetSystemStatus` -- метрики инфраструктуры
- `CheckDealStatus` -- проверка крипто-платежа

Компоненты собираются в `HiveCell` (cortex.py), который инициализирует 6 "Proteins" (навыков):
- **Persistence** -- CRUD к PostgreSQL/pgvector
- **Reasoning** -- DSPy/LLM-инференс (Mistral, OpenAI, Anthropic, Ollama)
- **Pulse** -- публикация событий в NATS JetStream (бинарный protobuf)
- **Telemetry** -- OpenTelemetry + Prometheus метрики
- **Guard** -- детерминистические гарантии безопасности
- **Transaction** -- Solana-платежи, шифрование секретов, конвертация цен

### 3.2 API Gateway (FastAPI, порт 8000)

REST-входная точка для внешних агентов:
- Верификация Ed25519 подписей
- Rate limiting через Redis
- Трансляция HTTP/JSON в gRPC
- OpenTelemetry distributed tracing
- Эндпоинты: `POST /v1/search`, `POST /v1/negotiate`, `POST /v1/deals/{id}/status`, `GET /v1/system/status`

### 3.3 Frontend (React + Vite + Tailwind, порт 3000)

"Agent Console" -- визуальный интерфейс в cyberpunk-стиле:
- Семантический поиск товаров
- Интерактивная переговорная панель с историей
- JIT UI рендеринг (динамические формы от сервера)
- Клиентский Ed25519 кошелек (tweetnacl)
- Фронтенд также следует ATCG-паттерну: `SearchAggregator`, `JITRenderer`, `AgentWallet`, `WalletMembrane`

### 3.4 Synapses (адаптеры)

- **Telegram Bot** -- бот для ручного взаимодействия с платформой через Telegram (`/search`, `/start`, inline-переговоры)
- **MCP Server** -- адаптер Model Context Protocol для интеграции с Claude Desktop, Cursor и другими LLM-клиентами. Автоматически генерирует Ed25519-кошелек, предоставляет tools: `search_hotels`, `negotiate_price`

### 3.5 Bee-Keeper Agent

Автономный агент-хранитель репозитория:
- Мониторит git diff на архитектурные "ереси"
- Проверяет соответствие ATCG-паттернам
- Публикует "Purity Reports" в GitHub
- Синхронизирует `llms.txt` при изменении protobuf
- Использует бюджетные модели (gpt-4o-mini) с fallback на Ollama

---

## 4. Shared Package -- `aura-core`

Пакет `packages/aura-core` -- "ДНК улья":
- Базовые протоколы/абстракции: `Aggregator`, `Transformer`, `Connector`, `Generator`, `Membrane`, `MetabolicLoop`
- Типы: `HiveContext`, `IntentAction`, `Observation`, `NegotiationOffer`, `SystemVitals`
- `SkillProtocol` и `SkillRegistry` -- реестр навыков
- Сгенерированные protobuf-стабы (`aura_core.gen`)

---

## 5. Protocol Buffers

Два основных proto-файла:

- **`negotiation.proto`** -- gRPC-контракт сервиса: `NegotiateRequest/Response`, `SearchRequest/Response`, `CheckDealStatus`, `CryptoPaymentInstructions`
- **`dna.proto`** -- универсальный "кровоток" для NATS JetStream: `Signal`, `Context`, `Intent`, `Observation`, `Event` с строго типизированными payload (oneof) и OTel trace context

Генерация через `buf generate` (betterproto для Python, ts-proto для TypeScript).

---

## 6. Инфраструктура

### Docker Compose (8 сервисов)

| Сервис | Образ | Назначение |
|--------|-------|------------|
| `db` | pgvector/pgvector:pg15 | PostgreSQL + векторный поиск |
| `redis` | redis:7-alpine | Кэширование, rate limiting, сессии |
| `nats` | nats:2.10-alpine | JetStream для event-driven коммуникации |
| `core` | custom | gRPC-движок |
| `api-gateway` | custom | REST gateway |
| `frontend` | custom | React SPA |
| `jaeger` | all-in-one | Distributed tracing |
| `prometheus` | prom/prometheus | Мониторинг метрик |
| `telegram-bot` | custom | Telegram-адаптер |

### Deploy

Helm-чарт для Kubernetes (`deploy/aura/`), включает Grafana dashboards, NATS, Jaeger, PVC для данных.

### CI/CD

GitHub Actions (`ci-cd.yaml`):
1. **Prepare** -- генерация protobuf-стабов
2. **Quality** -- lint (ruff, mypy, bandit, buf lint) + tests (pytest)
3. **Build** -- параллельная сборка 4 Docker-образов, push в GHCR
4. **Deploy** -- Helm upgrade на self-hosted runner

---

## 7. Технологический стек

| Слой | Технологии |
|------|------------|
| **Язык** | Python 3.12, TypeScript |
| **Backend** | gRPC, FastAPI, SQLAlchemy, DSPy, LiteLLM |
| **Frontend** | React 19, Vite 7, Tailwind CSS 4, Protobuf (ts-proto) |
| **LLM** | Mistral, OpenAI, Anthropic, Ollama (pluggable via LiteLLM) |
| **DB** | PostgreSQL 15 + pgvector, Redis 7 |
| **Messaging** | NATS JetStream (бинарный protobuf) |
| **Blockchain** | Solana (SOL/USDC) |
| **Observability** | OpenTelemetry, Jaeger, Prometheus, structlog |
| **Crypto** | Ed25519 (PyNaCl/tweetnacl), Fernet encryption |
| **Packaging** | uv, bun, buf, Docker, Helm |
| **CI** | GitHub Actions, pre-commit |

---

## 8. Ключевые архитектурные решения

- **Contract-First** -- все API определены в Protobuf, код генерируется
- **Binary Bloodstream** -- внутренняя коммуникация через бинарный protobuf (не JSON)
- **Hidden Knowledge** -- floor price никогда не раскрывается агентам
- **Multi-Strategy** -- переключаемые стратегии (rule / LLM / DSPy-compiled)
- **Semantic Caching** -- кэширование по семантическому хешу запроса
- **Fractal ATCG** -- один и тот же паттерн повторяется на уровне core, bee-keeper, frontend и synapses
- **Membrane Guards** -- детерминистические гарантии поверх вероятностных LLM-решений (prompt injection detection, floor price enforcement, DLP)
