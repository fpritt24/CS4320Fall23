"""Add unique to pr reviews

Revision ID: 8
Revises: 7
Create Date: 2023-02-24 13:10:53.862791

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8'
down_revision = '7'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('sourcepr-review-id', 'pull_request_reviews', schema='augur_data', type_='unique')
    op.create_unique_constraint('pr_review_unique', 'pull_request_reviews', ['pr_review_src_id'], schema='augur_data')
    
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('pr_review_unique', 'pull_request_reviews', schema='augur_data', type_='unique')
    op.create_unique_constraint('sourcepr-review-id', 'pull_request_reviews', ['pr_review_src_id', 'tool_source'], schema='augur_data')
    # ### end Alembic commands ###
