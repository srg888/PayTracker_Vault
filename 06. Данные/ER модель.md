ER-модель для системы трекинга платежей (17 таблиц). Разбита на две части: ядро процесса (заявки) и справочники/аудит. Диаграммы в формате mermaid — Obsidian отрисовывает их нативно (плагин mermaid встроен).

Поля `created_at` / `updated_at` (из `TimestampMixin`) есть у таблиц `REQUESTS`, `USERS`, `AGENTS`, `EXCHANGE_RATES`; на остальных таблицах они отсутствуют — точки во времени фиксируются через специализированные поля (например, `changed_at`, `uploaded_at`).

## Часть 1: ядро процесса

Заявка (`REQUESTS`) — общая таблица с полями, одинаковыми для всех типов заявок (см. [[00. Создание заявки|Создание заявки]]). Три таблицы-расширения (`PAYMENT_REQUESTS`, `PURCHASE_REQUESTS`, `CONSULTATION_REQUESTS`) хранят поля, специфичные под тип заявки (паттерн "таблица на тип" — table-per-type, см. [[Архитектурные решения|ADR-001]]), вместо одной гигантской таблицы с кучей NULL-полей.

Документы и требования к комплекту документов ссылаются на единый справочник [[Справочник типов документов]] — это решает проблему дублирования, которая была в старых заметках по процессам исполнения (см. [[Архитектурные решения|ADR-002]]).

```mermaid
erDiagram
  USERS ||--o{ REQUESTS : created_by
  USERS ||--o{ REQUESTS : executor_id
  DIVISIONS ||--o{ REQUESTS : contains
  REQUESTS ||--o| PAYMENT_REQUESTS : extends
  REQUESTS ||--o| PURCHASE_REQUESTS : extends
  REQUESTS ||--o| CONSULTATION_REQUESTS : extends
  REQUESTS ||--o{ STATUS_HISTORY : has
  REQUESTS ||--o{ COMMENTS : has
  REQUESTS ||--o{ DOCUMENTS : has
  REQUESTS ||--o{ REQUEST_DOC_REQUIREMENTS : has
  DOCUMENT_TYPES ||--o{ DOCUMENTS : classifies
  DOCUMENT_TYPES ||--o{ REQUEST_DOC_REQUIREMENTS : classifies

  USERS {
    int id PK
    string full_name
    string email UK
    string telegram_id UK
    string role
    bool is_active
    datetime created_at
    datetime updated_at
  }
  DIVISIONS {
    int id PK
    string name UK
  }
  REQUESTS {
    int id PK
    string number UK
    string type
    string status
    string title
    text description
    date expected_date
    int division_id FK
    int created_by_id FK
    int executor_id FK
    datetime submitted_at
    datetime closed_at
    datetime created_at
    datetime updated_at
  }
  PAYMENT_REQUESTS {
    int request_id PK
    text purpose
    text payment_purpose
    decimal amount
    int currency_id FK
    string recipient_name
    string recipient_country
    string recipient_address
    string recipient_bank
    string account_number_iban
    string swift_bic
    text additional_payment_info
    string payment_method
    int agent_id FK
    decimal rate_at_request
    decimal amount_rub_at_request
    decimal rate_at_execution
    decimal amount_rub_at_execution
  }
  PURCHASE_REQUESTS {
    int request_id PK
    int buyer_company_id FK
    string payment_method
    text markup_notes
    date delivery_date
  }
  CONSULTATION_REQUESTS {
    int request_id PK
    text question_description
  }
  STATUS_HISTORY {
    int id PK
    int request_id FK
    string from_status
    string to_status
    int changed_by_id FK
    text comment
    datetime changed_at
  }
  COMMENTS {
    int id PK
    int request_id FK
    int author_id FK
    text content
    datetime created_at
  }
  DOCUMENT_TYPES {
    string code PK
    string name
    string category
    bool is_required_default
  }
  DOCUMENTS {
    int id PK
    int request_id FK
    string document_type_code FK
    string file_name
    string storage_path
    bigint file_size_bytes
    int uploaded_by_id FK
    datetime uploaded_at
  }
  REQUEST_DOC_REQUIREMENTS {
    int id PK
    int request_id FK
    string document_type_code FK
    bool is_required_override
  }
```

## Часть 2: справочники, курсы валют, делегирование, аудит

```mermaid
erDiagram
  AGENTS ||--o{ PAYMENT_REQUESTS : agent
  BUYER_COMPANIES ||--o{ PURCHASE_REQUESTS : buyer
  CURRENCIES ||--o{ PAYMENT_REQUESTS : currency
  CURRENCIES ||--o{ EXCHANGE_RATES : rate_for
  USERS ||--o{ DELEGATIONS : delegator
  USERS ||--o{ DELEGATIONS : delegate
  USERS ||--o{ AUDIT_LOG : actor
  REQUESTS ||--o{ AUDIT_LOG : subject

  AGENTS {
    int id PK
    string code UK
    string name
    bool is_resident
    bool is_active
    datetime created_at
    datetime updated_at
  }
  BUYER_COMPANIES {
    int id PK
    string name UK
    bool is_active
  }
  CURRENCIES {
    int id PK
    string code UK
  }
  EXCHANGE_RATES {
    int id PK
    int currency_id FK
    date rate_date UK
    decimal rate_value
    bool is_stale
    datetime created_at
    datetime updated_at
  }
  DELEGATIONS {
    int id PK
    int delegator_id FK
    int delegate_id FK
    date start_date
    date end_date
    datetime revoked_at
  }
  AUDIT_LOG {
    int id PK
    string entity_type
    int entity_id
    int user_id FK
    string action_type
    string field_name
    text old_value
    text new_value
    datetime created_at
  }
  USERS {
    int id PK
    string full_name
  }
  PAYMENT_REQUESTS {
    int request_id PK
  }
  PURCHASE_REQUESTS {
    int request_id PK
  }
  REQUESTS {
    int id PK
  }
```

## Ключевые решения по модели

- **`REQUESTS.status`** — текущий статус хранится прямо в заявке (для быстрых выборок и фильтров в UI). `STATUS_HISTORY` — отдельный неизменяемый лог переходов, используется для аудита и отчётности по SLA (среднее время обработки, см. [[Отчётность]]). Текущий статус не восстанавливается из истории на каждый запрос — это денормализация ради производительности. Полная модель статусов — [[Статусы заявки]].
- **`REQUEST_DOC_REQUIREMENTS`** — таблица-исключение. По умолчанию обязательность документа берётся из `DOCUMENT_TYPES.is_required_default`, но Руководитель может переопределить перечень обязательных документов для конкретной заявки, не трогая общий справочник (см. [[09. Проверка комплектности и закрытие заявки|Проверка комплектности и закрытие заявки]] и [[Бизнес-правила|BR-052]]).
- **`AUDIT_LOG`** — универсальная таблица (`entity_type` + `entity_id`), а не отдельная таблица под каждый тип события. Проще в поддержке при 50-100 пользователях, чем плодить audit_requests, audit_documents и т.п. Соответствует требованиям из [[Аудит]].
- Один и тот же `USERS.id` встречается и как заказчик, и как исполнитель, и как участник делегирования — роль не жёстко зашита в отдельные таблицы, а определяется полем `role` и тем, в какой роли пользователь упомянут в конкретной заявке (см. [[Роли и права]]).
- `PAYMENT_REQUESTS` хранит `rate_at_request` / `rate_at_execution` — см. edge cases по курсу ЦБ в [[01. Поля заявки — Платёж|Поля заявки — Платёж]] и [[08. Фактическое исполнение платежа|Фактическое исполнение платежа]].

## Реализация
Модель уже реализована как SQLAlchemy 2.0 модели (17 таблиц) и первая Alembic-миграция под стек FastAPI/PostgreSQL — см. `paytracker/README.md` в этой же папке (`06. Данные/paytracker/`). Комментарии в коде моделей ссылаются на конкретные заметки этого vault. Проверено на PostgreSQL 16: `alembic upgrade head` / `alembic downgrade base` / повторный upgrade, сквозная запись/чтение через ORM. Соотносится с [[Архитектурные решения]] и [[Нефункциональные требования]].
