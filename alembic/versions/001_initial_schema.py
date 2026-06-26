"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-06-26 08:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create independent tables
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_categories_slug', 'categories', ['slug'], unique=True)

    op.create_table(
        'sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('base_url', sa.String(), nullable=False),
        sa.Column('article_list_url', sa.String(), nullable=False),
        sa.Column('language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=False),
        sa.Column('scrape_type', sa.Enum('PLAYWRIGHT', 'RSS', 'STATIC', name='scrapetype'), nullable=False),
        sa.Column('rate_limit_seconds', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_scrape_time', sa.DateTime(), nullable=True),
        sa.Column('success_count', sa.Integer(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('is_healthy', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sources_slug', 'sources', ['slug'], unique=True)

    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('READER', 'ADMIN', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_onboarded', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. Create stories table (without foreign key to articles yet)
    op.create_table(
        'stories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('primary_article_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Create articles table (it can now reference categories, sources, and stories)
    op.create_table(
        'articles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=False),
        sa.Column('source_url', sa.String(), nullable=False),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('publish_time', sa.DateTime(), nullable=False),
        sa.Column('author', sa.String(), nullable=True),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False),
        sa.Column('primary_article_id', sa.UUID(), nullable=True),
        sa.Column('story_id', sa.UUID(), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['primary_article_id'], ['articles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_articles_category_id', 'articles', ['category_id'], unique=False)
    op.create_index('ix_articles_language', 'articles', ['language'], unique=False)
    op.create_index('ix_articles_publish_time', 'articles', ['publish_time'], unique=False)
    op.create_index('ix_articles_source_id', 'articles', ['source_id'], unique=False)
    op.create_index('ix_articles_source_url', 'articles', ['source_url'], unique=True)

    # 4. Now add foreign key from stories to articles
    op.create_foreign_key(
        'fk_stories_primary_article_id',
        'stories', 'articles',
        ['primary_article_id'], ['id'],
        ondelete='SET NULL'
    )

    # 5. Create other dependent tables
    op.create_table(
        'article_embeddings',
        sa.Column('article_id', sa.UUID(), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('article_id')
    )

    op.create_table(
        'comments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('article_id', sa.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'interactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('article_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interactions_article_id', 'interactions', ['article_id'], unique=False)
    op.create_index('ix_interactions_user_id', 'interactions', ['user_id'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'snaps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('article_id', sa.UUID(), nullable=False),
        sa.Column('language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_snaps_article_id', 'snaps', ['article_id'], unique=True)
    op.create_index('ix_snaps_language', 'snaps', ['language'], unique=False)

    op.create_table(
        'story_articles',
        sa.Column('story_id', sa.UUID(), nullable=False),
        sa.Column('article_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('story_id', 'article_id')
    )

    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('primary_language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=False),
        sa.Column('secondary_language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=True),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )

    op.create_table(
        'snap_translations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('snap_id', sa.UUID(), nullable=False),
        sa.Column('language', sa.Enum('ENGLISH', 'HINDI', 'TAMIL', 'TELUGU', 'KANNADA', name='language'), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['snap_id'], ['snaps.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('snap_translations')
    op.drop_table('user_preferences')
    op.drop_table('story_articles')
    op.drop_index('ix_snaps_language', table_name='snaps')
    op.drop_index('ix_snaps_article_id', table_name='snaps')
    op.drop_table('snaps')
    op.drop_table('notifications')
    op.drop_index('ix_interactions_user_id', table_name='interactions')
    op.drop_index('ix_interactions_article_id', table_name='interactions')
    op.drop_table('interactions')
    op.drop_table('comments')
    op.drop_table('article_embeddings')

    # Remove foreign key constraint from stories before dropping articles
    op.drop_constraint('fk_stories_primary_article_id', 'stories', type_='foreignkey')

    op.drop_index('ix_articles_source_url', table_name='articles')
    op.drop_index('ix_articles_source_id', table_name='articles')
    op.drop_index('ix_articles_publish_time', table_name='articles')
    op.drop_index('ix_articles_language', table_name='articles')
    op.drop_index('ix_articles_category_id', table_name='articles')
    op.drop_table('articles')

    op.drop_table('stories')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
    op.drop_index('ix_sources_slug', table_name='sources')
    op.drop_table('sources')
    op.drop_index('ix_categories_slug', table_name='categories')
    op.drop_table('categories')

    # Drop Enum types in postgres
    sa.Enum(name='language').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='scrapetype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
