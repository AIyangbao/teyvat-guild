"""add fk: service_item.category_id -> category.id

Revision ID: 2db96ecd3bed
Revises: 67853ad23a52
Create Date: 2026-11-12 20:57:17.389240

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2db96ecd3bed'
down_revision: Union[str, Sequence[str], None] = '67853ad23a52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        "fk_service_item_category",          # ← 显式命名，回退时才知道删谁
        "service_item", "category",
        ["category_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_service_item_category",          # ← 同一个名字，drop 才能对上号
        "service_item", type_="foreignkey")
