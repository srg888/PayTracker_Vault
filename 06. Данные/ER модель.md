ER-модель для системы трекинга платежей. Разбита на две части: ядро процесса (заявки) и справочники/аудит. Диаграммы в формате mermaid — Obsidian отрисовывает их нативно (плагин mermaid встроен).

## Часть 1: ядро процесса

Заявка (`REQUESTS`) — общая таблица с полями, одинаковыми для всех типов заявок (см. [[00. Создание заявки|Создание заявки]]). Три таблицы-расширения (`PAYMENT_REQUESTS`, `PURCHASE_REQUESTS`, `CONSULTATION_REQUESTS`) хранят поля, специфичные под тип заявки (паттерн "таблица на тип" — table-per-type, см. [[Архитектурные решения|ADR-001]]), вместо одной гигантской таблицы с кучей NULL-полей.

Документы и требования к комплекту документов ссылаются на единый справочник [[Справочник типов документов]] — это решает проблему дублирования, которая была в старых заметках по процессам исполнения (см. [[Архитектурные решения|ADR-002]]).

```mermaid
erDiagram
  USERS ||--o{ REQUESTS : created_by
  USERS ||--o{ REQUESTS : requester_id
  USERS ||--o{ REQUESTS : executor_id
  DIVISIONS ||--o{ REQUESTS : contains
  REQUESTS ||--o| PAYMENT_REQUESTS : extends
  REQUESTS ||--o| PURCHASE_REQUESTS : extends
  REQUESTS ||--o| CONSULTATION_REQUESTS : extends
  REQUESTS ||--o{ STATUS_HISTORY : has
  REQUESTS ||--o{ COMMENTS : has
  REQUESTS ||--o{ DOCUMENTS : has
  REQUESTS ||--o{ REQUEST_DOC_REQUIREMENTS : has
  COMMENTS ||--o{ COMMENT_ATTACHMENTS : has
  PAYMENT_REQUESTS ||--o{ PAYMENT_TERMS_PROPOSALS : has
  DOCUMENT_TYPES ||--o{ DOCUMENTS : classifies
  DOCUMENT_TYPES ||--o{ REQUEST_DOC_REQUIREMENTS : classifies

  USERS {
    int id PK
    string full_name
    string role
  }
  DIVISIONS {
    int id PK
    string name
  }
  REQUESTS {
    int id PK
    string type
    string status
    string title
    date expected_date
    int created_by FK
    int requester_id FK
    int division_id FK
    int executor_id FK
  }
  PAYMENT_REQUESTS {
    int request_id PK
    decimal amount
    int currency_id FK
    int agent_id FK
    string payment_method
    decimal agreed_commission_amount
    decimal agreed_rate
  }
  PURCHASE_REQUESTS {
    int request_id PK
    int buyer_company_id FK
    string payment_method
    date delivery_date
  }
  CONSULTATION_REQUESTS {
    int request_id PK
    string question_text
  }
  STATUS_HISTORY {
    int id PK
    int request_id FK
    string from_status
    string to_status
    int changed_by FK
  }
  COMMENTS {
    int id PK
    int request_id FK
    int author_id FK
    string content
  }
  COMMENT_ATTACHMENTS {
    int id PK
    int comment_id FK
    string file_name
    string storage_path
    int uploaded_by_id FK
  }
  PAYMENT_TERMS_PROPOSALS {
    int id PK
    int payment_request_id FK
    string proposed_payment_method
    int proposed_agent_id FK
    decimal commission_amount
    decimal proposed_rate
    int proposed_by_id FK
    string decision
    string decision_comment
    int decided_by_id FK
  }
  DOCUMENT_TYPES {
    string code PK
    string name
    string category
  }
  DOCUMENTS {
    int id PK
    int request_id FK
    string document_type_code FK
    string file_name
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
    string code
    string name
  }
  BUYER_COMPANIES {
    int id PK
    string name
  }
  CURRENCIES {
    int id PK
    string code
  }
  EXCHANGE_RATES {
    int id PK
    int currency_id FK
    date rate_date
    decimal rate_value
    bool is_stale
  }
  DELEGATIONS {
    int id PK
    int delegator_id FK
    int delegate_id FK
    date start_date
    date end_date
  }
  AUDIT_LOG {
    int id PK
    string entity_type
    int entity_id FK
    int user_id FK
    string action_type
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
- **`REQUESTS.created_by` vs `REQUESTS.requester_id`** — разделены, чтобы поддержать создание заявки от имени Заказчика Руководителем/Исполнителем отдела: `created_by` — кто технически создал запись, `requester_id` — кто является Заказчиком по заявке (и чьи права на подтверждение/ответы на уточнения действуют). В обычном случае оба поля указывают на одного и того же пользователя (см. [[00. Создание заявки|Создание заявки]], [[Бизнес-правила|BR-014, BR-015]]).
- **`COMMENT_ATTACHMENTS`** — вложения к комментариям, отдельная от `DOCUMENTS` таблица: не типизируются через `DOCUMENT_TYPES` и не участвуют в проверке комплектности при закрытии заявки (см. [[Бизнес-правила|BR-054]]).
- **`PAYMENT_TERMS_PROPOSALS`** — история предложений условий исполнения платежа (способ, комиссия, курс), 1:N к `PAYMENT_REQUESTS` — намеренно отдельная таблица, а не поля в самой заявке, чтобы не терять историю при повторном предложении после отклонения (см. [[00a. Согласование условий исполнения (Платёж)|Согласование условий исполнения (Платёж)]], [[Бизнес-правила|BR-100–BR-102]]). Последнее принятое предложение дублируется в `PAYMENT_REQUESTS.agreed_commission_amount` / `agreed_rate` для быстрого доступа.
- `PAYMENT_REQUESTS` хранит `rate_at_request` / `rate_at_execution` (не показаны на диаграмме для краткости) — см. edge cases по курсу ЦБ в [[01. Поля заявки — Платёж|Поля заявки — Платёж]] и [[08. Фактическое исполнение платежа|Фактическое исполнение платежа]].

## Реализация
Модель уже реализована как SQLAlchemy 2.0 модели (19 таблиц) и Alembic-миграции под стек FastAPI/PostgreSQL — см. `paytracker/README.md` в этой же папке (`06. Данные/paytracker/`). Комментарии в коде моделей ссылаются на конкретные заметки этого vault. Проверено на PostgreSQL 16: `alembic upgrade head` / `alembic downgrade base` / повторный upgrade, сквозная запись/чтение через ORM. Соотносится с [[Архитектурные решения]] и [[Нефункциональные требования]].
