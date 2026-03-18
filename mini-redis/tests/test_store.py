import pytest
import threading
import time

import mini_redis.store as store_module
from mini_redis.store import MiniRedis


class FakeHashTable:
    """store 테스트를 위해 쓰는 아주 단순한 가짜 HashTable."""

    def __init__(self):
        # B 테스트는 HashTable의 계약만 필요하므로 dict로 흉내 낸다.
        self._data: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        """키-값 저장."""
        self._data[key] = value

    def get(self, key: str) -> str | None:
        """키 조회."""
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        """키 삭제."""
        return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        """키 존재 여부."""
        return key in self._data

    def keys(self) -> list[str]:
        """모든 키 목록."""
        return list(self._data.keys())

    def size(self) -> int:
        """현재 키 수."""
        return len(self._data)


@pytest.fixture(autouse=True)
def fake_hashtable(monkeypatch):
    """A 담당 구현이 없어도 B 테스트를 독립적으로 돌리기 위한 픽스처."""
    monkeypatch.setattr(store_module, "HashTable", FakeHashTable)


class TestMiniRedis:
    """B 담당: 동시성 + TTL 테스트"""

    def test_set_and_get(self):
        """기본 저장/조회"""
        r = MiniRedis()
        r.set("name", "alice")
        assert r.get("name") == "alice"
        r.shutdown()

    def test_get_nonexistent(self):
        """없는 키 조회 시 None"""
        r = MiniRedis()
        assert r.get("ghost") is None
        r.shutdown()

    def test_delete(self):
        """삭제 후 조회 시 None"""
        r = MiniRedis()
        r.set("name", "alice")
        assert r.delete("name") is True
        assert r.get("name") is None
        r.shutdown()

    def test_ttl_expiry(self):
        """TTL 만료 후 None 반환"""
        r = MiniRedis()
        r.set("temp", "data", ttl=1)
        assert r.get("temp") == "data"
        time.sleep(1.5)
        assert r.get("temp") is None
        r.shutdown()

    def test_ttl_remaining(self):
        """남은 TTL 확인"""
        r = MiniRedis()
        r.set("temp", "data", ttl=10)
        remaining = r.ttl("temp")
        assert remaining is not None and remaining > 0
        r.shutdown()

    def test_ttl_no_expiry(self):
        """TTL 없는 키 -> None"""
        r = MiniRedis()
        r.set("perm", "data")
        assert r.ttl("perm") is None
        r.shutdown()

    def test_ttl_nonexistent(self):
        """없는 키 TTL -> -1"""
        r = MiniRedis()
        assert r.ttl("ghost") == -1
        r.shutdown()

    def test_periodic_cleanup(self):
        """백그라운드 스레드가 만료 키를 자동 정리"""
        r = MiniRedis(cleanup_interval=0.5)
        r.set("temp", "data", ttl=1)
        time.sleep(2)
        assert "temp" not in r.keys()
        r.shutdown()

    def test_concurrent_writes(self):
        """멀티스레드 동시 쓰기 -> 데이터 손실 없음"""
        r = MiniRedis()
        errors = []

        def writer(prefix, count):
            try:
                for i in range(count):
                    r.set(f"{prefix}_{i}", f"val_{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(f"t{idx}", 100)) for idx in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0
        assert r.info()["total_keys"] == 500
        r.shutdown()

    def test_concurrent_read_write(self):
        """읽기와 쓰기가 동시에 발생해도 에러 없음"""
        r = MiniRedis()
        r.set("shared", "initial")
        errors = []

        def reader(count):
            try:
                for _ in range(count):
                    r.get("shared")
            except Exception as exc:
                errors.append(exc)

        def writer(count):
            try:
                for i in range(count):
                    r.set("shared", f"val_{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=reader, args=(200,)),
            threading.Thread(target=writer, args=(200,)),
            threading.Thread(target=reader, args=(200,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0
        r.shutdown()

    def test_flush(self):
        """flush 후 모든 데이터 삭제"""
        r = MiniRedis()
        for i in range(10):
            r.set(f"k{i}", f"v{i}")
        r.flush()
        assert r.info()["total_keys"] == 0
        r.shutdown()

    def test_info(self):
        """info 반환값 구조 확인"""
        r = MiniRedis()
        r.set("a", "1", ttl=60)
        r.set("b", "2")
        info = r.info()
        assert info["total_keys"] == 2
        assert info["keys_with_ttl"] == 1
        assert info["keys_without_ttl"] == 1
        r.shutdown()

    def test_invalidate(self):
        """invalidate는 의미만 다르고 삭제처럼 동작"""
        r = MiniRedis()
        r.set("session", "token")
        assert r.invalidate("session") is True
        assert r.exists("session") is False
        r.shutdown()
