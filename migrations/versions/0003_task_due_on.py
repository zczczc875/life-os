"""Add an optional calendar deadline to tasks.

Revision ID: 0003_task_due_on
Revises: 0002_tasks
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_task_due_on"
down_revision = "0002_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("due_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "due_on")
