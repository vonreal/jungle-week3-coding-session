import pytest

from mini_redis.hashtable import HashTable


class TestHashTable:
    """A 담당: 해시 테이블 단위 테스트"""

    def test_set_and_get(self):
        """기본 저장/조회"""
        pass

    def test_overwrite(self):
        """동일 키 덮어쓰기"""
        pass

    def test_delete(self):
        """삭제 후 조회 시 None"""
        pass

    def test_collision(self):
        """해시 충돌 시 chaining 동작"""
        pass

    def test_resize(self):
        """load factor 초과 시 resize + 데이터 보존"""
        pass

