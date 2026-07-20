"""payment terms negotiation, manager review before closing

Adds support for:
- Согласование условий исполнения платежа (BR-100..102): payment_terms_proposals
  table (history of способ/комиссия/курс proposals + Заказчик decision), plus
  payment_requests.agreed_commission_amount / agreed_rate (last accepted proposal,
  denormalized for quick access). payment_requests.payment_method becomes nullable —
  it is now set when a proposal is accepted, not at request creation.
- Проверка Руководителем и закрытие (BR-110..111): new request_status values
  'terms_proposed' and 'manager_review'.
- New audit_action_type values for the above.

Revision ID: c4d8f27a9b13
Revises: b7a291e6c9d4
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8f27a9b13'
down_revision: Union[str, Sequence[str], None] = 'b7a291e6c9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # --- payment_terms_decision enum ----------------------------------------------
    payment_terms_decision = sa.Enum(
        'pending', 'accepted', 'rejected', name='payment_terms_decision'
    )
    payment_terms_decision.create(op.get_bind(), checkfirst=True)

    # --- request_status / audit_action_type: new values -----------------------------
    # See note in b7a291e6c9d4 re: PostgreSQL 12+ requirement for ADD VALUE in a
    # transaction. Tested against PostgreSQL 16 per paytracker/README.md.
    op.execute("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'terms_proposed'")
    op.execute("ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'manager_review'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'terms_proposed'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'terms_accepted'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'terms_rejected'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'sent_for_manager_review'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'rework_requested'")
    op.execute("ALTER TYPE audit_action_type ADD VALUE IF NOT EXISTS 'closed_by_manager'")

    # --- payment_requests: payment_method nullable, agreed_* columns ----------------
    op.alter_column('payment_requests', 'payment_method', nullable=True)
    op.add_column('payment_requests', sa.Column('agreed_commission_amount', sa.Numeric(18, 2), nullable=True))
    op.add_column('payment_requests', sa.Column('agreed_rate', sa.Numeric(18, 6), nullable=True))

    # --- payment_terms_proposals -----------------------------------------------------
    op.create_table(
        'payment_terms_proposals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_request_id', sa.Integer(), nullable=False),
        sa.Column('proposed_payment_method', sa.Enum('bank', 'agent', name='payment_method'), nullable=False),
        sa.Column('proposed_agent_id', sa.Integer(), nullable=True),
        sa.Column('commission_amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('proposed_rate', sa.Numeric(18, 6), nullable=False),
        sa.Column('proposed_by_id', sa.Integer(), nullable=False),
        sa.Column('proposed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decision', payment_terms_decision, nullable=False, server_default='pending'),
        sa.Column('decision_comment', sa.Text(), nullable=True),
        sa.Column('decided_by_id', sa.Integer(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['payment_request_id'], ['payment_requests.request_id'],
            name=op.f('fk_payment_terms_proposals_payment_request_id_payment_requests'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['proposed_agent_id'], ['agents.id'],
            name=op.f('fk_payment_terms_proposals_proposed_agent_id_agents'),
        ),
        sa.ForeignKeyConstraint(
            ['proposed_by_id'], ['users.id'],
            name=op.f('fk_payment_terms_proposals_proposed_by_id_users'),
        ),
        sa.ForeignKeyConstraint(
            ['decided_by_id'], ['users.id'],
            name=op.f('fk_payment_terms_proposals_decided_by_id_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_terms_proposals')),
    )
    op.create_index(
        op.f('ix_payment_terms_proposals_payment_request_id'),
        'payment_terms_proposals', ['payment_request_id'],
    )


def downgrade() -> None:
    """Downgrade schema.

    Note: as in b7a291e6c9d4, PostgreSQL does not support removing values from an
    existing ENUM type in place — downgrading request_status/audit_action_type would
    require recreating those types. Not done here automatically; drop any rows using
    the new values first if a full downgrade is required.
    """
    op.drop_index(op.f('ix_payment_terms_proposals_payment_request_id'), table_name='payment_terms_proposals')
    op.drop_table('payment_terms_proposals')
    op.drop_column('payment_requests', 'agreed_rate')
    op.drop_column('payment_requests', 'agreed_commission_amount')
    op.alter_column('payment_requests', 'payment_method', nullable=False)
    op.execute('DROP TYPE IF EXISTS payment_terms_decision')
