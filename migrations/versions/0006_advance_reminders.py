"""Track which advance reminders have been handled for each current deadline.

Revision ID: 0006_advance_reminders
Revises: 0005_task_reminders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_advance_reminders"
down_revision = "0005_task_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("advance_reminder_mask", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tasks", "advance_reminder_mask")
