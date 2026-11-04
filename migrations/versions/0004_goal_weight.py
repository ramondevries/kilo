# Kilo Tracker - a small weight-tracking web app.
# Copyright (C) 2026 Ramón de Vries <ramon@11tools.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See the LICENSE file for the full text.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""A goal weight: user.goal_weight_kg, goal_losing, trend_days and public_show_goal.

Existing users get no goal, a 30-day trend for the goal date and the goal hidden on their public
chart, so nothing they see changes until they set a goal.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("goal_weight_kg", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("goal_losing", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("trend_days", sa.Integer(), nullable=False, server_default="30"))
        batch_op.add_column(sa.Column("public_show_goal", sa.Boolean(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("public_show_goal")
        batch_op.drop_column("trend_days")
        batch_op.drop_column("goal_losing")
        batch_op.drop_column("goal_weight_kg")
