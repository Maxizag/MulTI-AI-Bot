"""Set default values for existing users

Revision ID: 175acc40e3a8
Revises: 010a0a92691c
Create Date: 2026-01-17 14:52:14.873084

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '175acc40e3a8'
down_revision: Union[str, Sequence[str], None] = '010a0a92691c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
def upgrade() -> None:
    # Устанавливаем дефолтные значения для существующих пользователей
    op.execute("""
        UPDATE users 
        SET 
            subscription_tier = COALESCE(subscription_tier, 'free'),
            tokens_used_month = COALESCE(tokens_used_month, 0),
            tokens_limit_month = COALESCE(tokens_limit_month, 100000),
            last_token_reset = COALESCE(last_token_reset, datetime('now')),
            total_spent_usd = COALESCE(total_spent_usd, 0.0)
        WHERE subscription_tier IS NULL 
           OR tokens_used_month IS NULL 
           OR tokens_limit_month IS NULL
           OR total_spent_usd IS NULL
    """)


def downgrade() -> None:
    # Откат не требуется
    pass