# PayTracker — модели и миграция БД

## Состав
- `app/db/base_class.py` — declarative Base с naming convention (важно для стабильного autogenerate).
- `app/models/` — все модели SQLAlchemy 2.0 (Mapped/mapped_column), 17 таблиц.
- `alembic/` — конфигурация Alembic, `alembic/versions/..._initial_schema.py` — первая миграция.

Модель полностью соответствует ER-диаграмме и .md файлам из Obsidian vault
(комментарии в коде моделей ссылаются на конкретные заметки).

## Как использовать в существующем проекте

1. Скопировать `app/db/base_class.py`, `app/models/*` в свой проект (или смёрджить с существующими,
   если у тебя уже есть `app/db/base_class.py` — тогда просто добавь модели).
2. Скопировать `alembic/` и `alembic.ini`, если Alembic ещё не настроен, либо перенести только
   файл миграции `alembic/versions/7fe16b3def34_initial_schema.py` в свой существующий alembic/versions/,
   поправив `down_revision`, если у тебя уже есть предыдущие миграции.
3. Задать переменную окружения `DATABASE_URL`, например:
   `postgresql+psycopg2://user:password@db:5432/paytracker`
4. Накатить миграцию: `alembic upgrade head`

## Что уже проверено (не просто сгенерировано, а реально прогнано на PostgreSQL 16)
- `alembic upgrade head` — создаёт все 17 таблиц, 6 ENUM-типов (без дублей — payment_method
  переиспользуется между payment_requests и purchase_requests), все FK и constraints с
  предсказуемыми именами.
- `alembic downgrade base` — полностью откатывает схему, включая ENUM-типы.
- Повторный `alembic upgrade head` после downgrade — проходит чисто (эта проверка вскрыла
  и исправила баг: Alembic по умолчанию не удаляет ENUM-типы при drop_table в PostgreSQL,
  это дописано вручную в конце downgrade()).
- Сквозная вставка/чтение данных через ORM (заявка → платёжные детали → комментарии →
  документы → аудит-лог) — работает через реальные модели, не только "голый" DDL.

## Дальнейшие миграции
Дальше новые миграции пишутся через `alembic revision --autogenerate -m "..."` после
изменения моделей — так же, как была сгенерирована эта, первая.

### `b7a291e6c9d4` — requester_id, вложения к комментариям, самоназначение
Добавляет:
- `requests.requester_id` — Заказчик, отдельно от `created_by_id` (см. "Создание заявки от
  имени Заказчика", Бизнес-правила BR-015). Бэкафилл существующих строк значением `created_by_id`.
- `request_comment_attachments` — вложения к комментариям (Бизнес-правила BR-054).
- Новые значения `audit_action_type`: `created_for_requester`, `executor_self_assigned`,
  `comment_attachment_uploaded` (BR-023, BR-054). На PostgreSQL < 12 добавление значений
  ENUM нужно выполнить отдельными выражениями вне транзакции.

### `c4d8f27a9b13` — согласование условий исполнения платежа, проверка Руководителем
Добавляет:
- `payment_terms_proposals` — история предложений условий исполнения платежа (способ,
  комиссия, курс) и решений Заказчика (Бизнес-правила BR-100–BR-102).
- `payment_requests.agreed_commission_amount`, `agreed_rate` — последнее принятое
  предложение, для быстрого доступа. `payment_requests.payment_method` становится
  nullable — заполняется при согласовании условий, а не при создании заявки.
- Новые значения `request_status`: `terms_proposed`, `manager_review`.
- Новые значения `audit_action_type`: `terms_proposed`, `terms_accepted`,
  `terms_rejected`, `sent_for_manager_review`, `rework_requested`, `closed_by_manager`
  (BR-100–BR-102, BR-110–BR-111).
