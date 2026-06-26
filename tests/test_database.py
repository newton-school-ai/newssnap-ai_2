"""Tests for database models, relationships, and constraints."""

import uuid
from datetime import datetime

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from src.config.settings import Language, ScrapeType, UserRole, settings
from src.models import (
    Article,
    Category,
    Comment,
    Interaction,
    Snap,
    Source,
    User,
)


def test_models_exist_and_query():
    """Verify all 10 core tables exist in the database."""
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = [
        "users", "user_preferences", "categories", "sources",
        "articles", "article_embeddings", "snaps", "snap_translations",
        "stories", "story_articles", "interactions", "comments", "notifications"
    ]
    for table in expected_tables:
        assert table in tables, f"Table {table} not found in database"


def test_timestamp_mixin():
    """Verify models automatically populate created_at and updated_at."""
    engine = create_engine(settings.DATABASE_URL)
    session_class = sessionmaker(bind=engine)
    session = session_class()

    try:
        # Create a category to test
        test_slug = f"test_cat_{uuid.uuid4().hex[:8]}"
        category = Category(
            slug=test_slug,
            name="Test Category",
            is_active=True
        )
        session.add(category)
        session.commit()

        # Refresh from database
        session.refresh(category)

        # Verify timestamps are populated
        assert category.created_at is not None
        assert category.updated_at is not None
        assert isinstance(category.created_at, datetime)
        assert isinstance(category.updated_at, datetime)

        # Cleanup
        session.delete(category)
        session.commit()
    finally:
        session.close()


def test_article_cascading_deletes():
    """Verify that deleting an Article cascades to snaps, interactions, and comments."""
    engine = create_engine(settings.DATABASE_URL)
    session_class = sessionmaker(bind=engine)
    session = session_class()

    try:
        # 1. Ensure/get helper objects (Category and Source)
        category = session.query(Category).first()
        if not category:
            category = Category(slug="national", name="National", is_active=True)
            session.add(category)
            session.commit()
            session.refresh(category)

        source = session.query(Source).first()
        if not source:
            source = Source(
                id=uuid.uuid4(),
                slug="test_source",
                name="Test Source",
                base_url="https://test.com",
                article_list_url="https://test.com/news",
                language=Language.ENGLISH,
                scrape_type=ScrapeType.STATIC,
                is_active=True,
                is_healthy=True,
            )
            session.add(source)
            session.commit()
            session.refresh(source)

        user = session.query(User).first()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email="cascade_test@example.com",
                name="Cascade Test User",
                role=UserRole.READER,
                is_active=True,
                is_onboarded=True
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        # 2. Insert Article
        article_id = uuid.uuid4()
        article = Article(
            id=article_id,
            title="Test Cascade Article",
            body="This article is used to verify cascading deletes.",
            source_id=source.id,
            category_id=category.id,
            language=Language.ENGLISH,
            source_url=f"https://test.com/cascade-{uuid.uuid4().hex[:8]}",
            publish_time=datetime.utcnow(),
            is_duplicate=False,
        )
        session.add(article)
        session.flush()

        # 3. Create dependent entities
        snap = Snap(
            id=uuid.uuid4(),
            article_id=article_id,
            summary="Test Snap Summary",
            language=Language.ENGLISH
        )
        session.add(snap)

        interaction = Interaction(
            id=uuid.uuid4(),
            user_id=user.id,
            article_id=article_id,
            type="like"
        )
        session.add(interaction)

        comment = Comment(
            id=uuid.uuid4(),
            user_id=user.id,
            article_id=article_id,
            content="Test Comment Body"
        )
        session.add(comment)

        session.commit()

        # Verify insertion
        assert session.query(Snap).filter_by(article_id=article_id).count() == 1
        assert session.query(Interaction).filter_by(article_id=article_id).count() == 1
        assert session.query(Comment).filter_by(article_id=article_id).count() == 1

        # Delete the article
        session.delete(article)
        session.commit()

        # Verify cascades (count should be 0)
        assert session.query(Snap).filter_by(article_id=article_id).count() == 0
        assert session.query(Interaction).filter_by(article_id=article_id).count() == 0
        assert session.query(Comment).filter_by(article_id=article_id).count() == 0

    finally:
        session.close()


def test_required_indexes_exist():
    """Verify that required indexes exist on articles, interactions, and snaps."""
    engine = create_engine(settings.DATABASE_URL)
    inspector = inspect(engine)

    # 1. Articles indexes
    assert any("publish_time" in idx or "publish_time" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("articles") for idx in [idx_info]), "publish_time index missing on articles"
    assert any("language" in idx or "language" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("articles") for idx in [idx_info]), "language index missing on articles"
    assert any("source_id" in idx or "source_id" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("articles") for idx in [idx_info]), "source_id index missing on articles"

    # 2. Interactions indexes
    assert any("user_id" in idx or "user_id" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("interactions") for idx in [idx_info]), "user_id index missing on interactions"
    assert any("article_id" in idx or "article_id" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("interactions") for idx in [idx_info]), "article_id index missing on interactions"

    # 3. Snaps indexes
    assert any("article_id" in idx or "article_id" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("snaps") for idx in [idx_info]), "article_id index missing on snaps"
    assert any("language" in idx or "language" in "".join(idx_info["column_names"])
               for idx_info in inspector.get_indexes("snaps") for idx in [idx_info]), "language index missing on snaps"
