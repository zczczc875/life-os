"""Add an optional local time to task deadlines.

Revision ID: 0004_task_due_time
Revises: 0003_task_due_on
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_task_due_time"
down_revision = "0003_task_due_on"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "due_time",
            sa.Time(),
            sa.CheckConstraint(
                "due_time IS NULL OR due_on IS NOT NULL",
                name="ck_tasks_due_time_date",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "due_time")
