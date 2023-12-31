"""change CollectionStatus table to keep track of facade independently

Revision ID: 6
Revises: 5
Create Date: 2023-02-16 12:45:57.486871

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision = '6'
down_revision = '5'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    
    op.drop_column('repo', 'repo_status', schema='augur_data')
    op.add_column('collection_status', sa.Column('facade_status', sa.String(), server_default=sa.text("'Pending'"), nullable=False), schema='augur_operations')
    op.add_column('collection_status', sa.Column('facade_data_last_collected', postgresql.TIMESTAMP(), nullable=True), schema='augur_operations')
    op.add_column('collection_status', sa.Column('facade_task_id', sa.String(), nullable=True), schema='augur_operations')

    #Add toggle for facade collection.
    conn = op.get_bind()
    result = conn.execute(text("""SELECT * FROM augur_operations.config WHERE section_name='Task_Routine';""")).fetchall()
    if result:

        conn.execute(text(f"""
            INSERT INTO "augur_operations"."config" ("section_name", "setting_name", "value", "type") VALUES ('Task_Routine', 'facade_phase', '{1}', 'int');
            INSERT INTO "augur_operations"."config" ("section_name", "setting_name", "value", "type") VALUES ('Facade', 'run_facade_contributors', '{1}', 'int');
            """))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('collection_status', 'facade_task_id', schema='augur_operations')
    op.drop_column('collection_status', 'facade_data_last_collected', schema='augur_operations')
    op.drop_column('collection_status', 'facade_status', schema='augur_operations')
    op.add_column('repo', sa.Column('repo_status', sa.VARCHAR(), server_default=sa.text("'New'::character varying"), autoincrement=False, nullable=False), schema='augur_data')
    # ### end Alembic commands ###
