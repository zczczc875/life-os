"""create tasks table

Revision ID: 0002_tasks
Revises: 0001_app_settings
Create Date: 2026-11-04

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_tasks"
down_revision: str | None = "0001_app_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.CheckConstraint(
            "status IN ('pending', 'completed')",
            name=op.f("ck_tasks_status"),
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL)"
            " OR (status = 'pending' AND completed_at IS NULL)",
            name=op.f("ck_tasks_completed_at"),
        ),
    )
    op.create_index(
        "ix_tasks_created_at_id",
        "tasks",
        [sa.text("created_at DESC"), "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_created_at_id", table_name="tasks")
    op.drop_table("tasks")
