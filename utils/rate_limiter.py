import time
from enum import Enum
from typing import Dict, List
from dataclasses import dataclass


class RateLimitType(Enum):
    DOWNLOAD = "download"
    COMMAND = "command"
    SEARCH = "search"


@dataclass
class RateLimit:
    max_requests: int
    window_seconds: int
    requests: List[float]


class RateLimitManager:
    def __init__(self):
        self.limits: Dict[int, Dict[RateLimitType, RateLimit]] = {}

    def _ensure_user(self, user_id: int):
        if user_id not in self.limits:
            self.limits[user_id] = {}

    def _cleanup_old_requests(self, rate_limit: RateLimit):
        now = time.time()
        rate_limit.requests = [
            req_time
            for req_time in rate_limit.requests
            if now - req_time < rate_limit.window_seconds
        ]

    def add_limit(
        self,
        user_id: int,
        limit_type: RateLimitType,
        max_requests: int,
        window_seconds: int,
    ):
        self._ensure_user(user_id)
        self.limits[user_id][limit_type] = RateLimit(
            max_requests=max_requests, window_seconds=window_seconds, requests=[]
        )

    def is_allowed(self, user_id: int, limit_type: RateLimitType) -> bool:
        self._ensure_user(user_id)
        if limit_type not in self.limits[user_id]:
            return True
        rate_limit = self.limits[user_id][limit_type]
        self._cleanup_old_requests(rate_limit)
        return len(rate_limit.requests) < rate_limit.max_requests

    def record_request(self, user_id: int, limit_type: RateLimitType):
        self._ensure_user(user_id)
        if limit_type not in self.limits[user_id]:
            return
        rate_limit = self.limits[user_id][limit_type]
        rate_limit.requests.append(time.time())

    def get_remaining(self, user_id: int, limit_type: RateLimitType) -> int:
        self._ensure_user(user_id)
        if limit_type not in self.limits[user_id]:
            return float("inf")
        rate_limit = self.limits[user_id][limit_type]
        self._cleanup_old_requests(rate_limit)
        return max(0, rate_limit.max_requests - len(rate_limit.requests))


def create_rate_limit_manager_from_config(config):
    manager = RateLimitManager()
    # Inicializar límites basados en config si es necesario
    return manager
