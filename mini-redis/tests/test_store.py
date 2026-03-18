import pytest

from mini_redis.store import MiniRedis


class TestMiniRedis:
    """B 담당: 동시성 + TTL 테스트"""

    def test_set_and_get(self):
        """기본 저장/조회"""
        pass

    def test_ttl_expiry(self):
        """TTL 만료 후 None 반환"""
        pass

    def test_concurrent_access(self):
        """멀티스레드 동시 읽기/쓰기"""
        pass

