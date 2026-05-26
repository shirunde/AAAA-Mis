import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'mis-secret-key-change-in-production'

    # MySQL connection config
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or '123456'
    DB_NAME = os.environ.get('DB_NAME') or 'mis_system'
    DB_CHARSET = 'utf8mb4'

    # Connection pool config
    DB_POOL_MIN_CACHED = 2
    DB_POOL_MAX_CACHED = 10
    DB_POOL_MAX_CONNECTIONS = 20

    # Pagination
    PER_PAGE = 15

    # Grade weights
    REGULAR_WEIGHT = 0.3
    EXAM_WEIGHT = 0.7
