"""Track the reminder claimed for each task's current deadline.

Revision ID: 0005_task_reminders
Revises: 0004_task_due_time
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_task_reminders"
down_revision = "0004_task_due_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("reminder_claimed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "reminder_claimed_at")
