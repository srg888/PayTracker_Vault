"""requester_id split from created_by, comment attachments, self-assign audit action

Adds support for:
- Создание заявки от имени Заказчика (BR-015): requests.requester_id, separate from
  requests.created_by_id. Backfilled from created_by_id for existing rows, then made NOT NULL.
- Самостоятельное назначение исполнителя (BR-023): new AuditActionType value, no schema change
  needed beyond the enum (executor_id / status machine already support this).
- Вложения к комментариям (BR-054): new table request_comment_attachments.

Revision ID: b7a291e6c9d4
Revises: 7fe16b3def34
Create Date: 2026-07-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7a291e6c9d4'
down_revision: Union[str, Sequence[str], None] = '7fe16b3def34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # --- requests.requester_id ---------------------------------------------------
    # Добавляем nullable, бэкафилим значением created_by_id (по умолчанию Заказчик =
    # тот, кто создал заявку), затем делаем NOT NULL и добавляем FK/индекс.
    op.add_column('requests', sa.Column('requester_id', sa.Integer(), nullable=True))
    op.execute('UPDATE requests SET requester_id = created_by_id WHERE requester_id IS NULL')
    op.alter_column('requests', 'requester_id', nullable=False)
    op.create_foreign_key(
        op.f('fk_requests_requester_id_users'), 'requests', 'users', ['requester_id'], ['id']
    )
    op.create_index(op.f('ix_requests_requester_id'), 'requests', ['requester_id'])

    # --- request_comment_attachments ----------------------------------------------
    op.create_table(
        'request_comment_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('comment_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=1024), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['comment_id'], ['request_comments.id'],
            name=op.f('fk_request_comment_attachments_comment_id_request_comments'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['uploaded_by_id'], ['users.id'],
            name=op.f('fk_request_comment_attachments_uploaded_by_id_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_request_comment_attachments')),
    )

    # --- audit_action_type: new values --------------------------------------------
    # ALTER TYPE ... ADD VALUE requires PostgreSQL 12+ to run inside a transaction;
    # tested against PostgreSQL 16 per paytracker/README.md. If running on an older
    # setup, run these three statements manually outside of a transaction instead.
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'created_for_requester'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'executor_self_assigned'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'comment_attachment_uploaded'")


def downgrade() -> None:
    """Downgrade schema.

    Note: PostgreSQL does not support removing values from an existing ENUM type
    in place. Downgrading audit_action_type would require recreating the type
    (rename old, create new without the added values, cast column, drop old) — not
    done here automatically since it would fail if any audit_log rows already use
    the new values. Drop those rows first if a full downgrade is required.
    """
    op.drop_table('request_comment_attachments')
    op.drop_index(op.f('ix_requests_requester_id'), table_name='requests')
    op.drop_constraint(op.f('fk_requests_requester_id_users'), 'requests', type_='foreignkey')
    op.drop_column('requests', 'requester_id')
