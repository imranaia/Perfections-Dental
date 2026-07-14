# backend/config.py
# =========================================
# Perfections Dental Services
# Configuration Module - v1.0
# =========================================

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SESSION_TYPE = os.getenv('SESSION_TYPE', 'filesystem')
    SESSION_PERMANENT = os.getenv('SESSION_PERMANENT', 'False') == 'True'
    SESSION_USE_SIGNER = os.getenv('SESSION_USE_SIGNER', 'True') == 'True'
    SESSION_COOKIE_SECURE = os.getenv(
        'SESSION_COOKIE_SECURE', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = os.getenv(
        'SESSION_COOKIE_HTTPONLY', 'True') == 'True'
    SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')

    # Database — SQLite file, lives alongside the schema/seed scripts
    DB_PATH = os.getenv(
        'DB_PATH',
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'database', 'perfections_dental.db')
    )


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Enable in production with HTTPS


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    SESSION_COOKIE_SECURE = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
