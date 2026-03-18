import threading
import time

from mini_redis.store import MiniRedis


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

    def test_zero_ttl_expires_immediately(self):
        """TTL 0초 키는 즉시 만료돼야 한다"""
        r = MiniRedis()
        r.set("flash", "value", ttl=0)
        assert r.get("flash") is None
        assert r.ttl("flash") == -1
        r.shutdown()

    def test_negative_ttl_behaves_like_expired_key(self):
        """음수 TTL도 이미 만료된 키처럼 처리해야 한다"""
        r = MiniRedis()
        r.set("expired", "value", ttl=-3)
        assert r.exists("expired") is False
        assert r.get("expired") is None
        r.shutdown()

    def test_overwrite_without_ttl_clears_previous_expiry(self):
        """TTL 있던 키를 TTL 없이 덮어쓰면 만료 기록이 지워져야 한다"""
        r = MiniRedis()
        r.set("session", "token", ttl=1)
        r.set("session", "renewed")
        time.sleep(1.1)
        assert r.get("session") == "renewed"
        assert r.ttl("session") is None
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

    def test_flush_clears_expiry_bookkeeping(self):
        """flush는 TTL 장부까지 함께 비워야 한다"""
        r = MiniRedis()
        r.set("short", "1", ttl=60)
        r.set("long", "2", ttl=120)
        r.flush()
        assert r._expiry == {}
        assert r.keys() == []
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

    def test_shutdown_stops_cleanup_thread(self):
        """shutdown 뒤에는 청소부 스레드가 멈춰야 한다"""
        r = MiniRedis(cleanup_interval=0.05)
        r.shutdown()
        assert r._cleanup_thread.is_alive() is False
