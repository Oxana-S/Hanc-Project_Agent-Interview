"""Storage module — хранение данных."""

from src.storage.redis import RedisStorageManager
from src.storage.postgres import PostgreSQLStorageManager

__all__ = [
    "RedisStorageManager",
    "PostgreSQLStorageManager",
]
