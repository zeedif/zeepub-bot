# __init__.py
"""
ZeePub Bot - Telegram bot for EPUB management and distribution

A modular, refactored Telegram bot that handles OPDS feeds,
EPUB downloads, metadata extraction, and book publishing.
"""

__version__ = "2.0.0"
__author__ = "ZeePub Team"
__description__ = "Telegram bot for EPUB management and distribution"

# Make main components available at package level
from config.config_settings import config
from core.session_manager import session_manager
from core.state_manager import state_manager

__all__ = ['config', 'session_manager', 'state_manager']