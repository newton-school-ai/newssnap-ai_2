"""NewsSnap AI - Database models export."""

from src.models.article import Article, ArticleEmbedding
from src.models.base import Base
from src.models.category import Category
from src.models.interaction import Comment, Interaction
from src.models.notification import Notification
from src.models.snap import Snap, SnapTranslation
from src.models.source import Source
from src.models.story import Story, StoryArticle
from src.models.user import User, UserPreference

__all__ = [
    "Base",
    "User",
    "UserPreference",
    "Category",
    "Source",
    "Article",
    "ArticleEmbedding",
    "Snap",
    "SnapTranslation",
    "Story",
    "StoryArticle",
    "Interaction",
    "Comment",
    "Notification",
]
