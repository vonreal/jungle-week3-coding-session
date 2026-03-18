import pytest

from mini_redis.hashtable import HashTable


class TestHashTable:
    """A 담당: 해시 테이블 단위 테스트"""

    def test_set_and_get(self):
        """기본 저장/조회"""
        ht = HashTable()
        ht.set("name", "alice")
        assert ht.get("name") == "alice"

    def test_overwrite(self):
        """동일 키 덮어쓰기"""
        ht = HashTable()
        ht.set("name", "alice")
        ht.set("name", "bob")
        assert ht.get("name") == "bob"
        assert ht.size() == 1

    def test_get_nonexistent(self):
        """없는 키 조회 시 None"""
        ht = HashTable()
        assert ht.get("ghost") is None

    def test_delete_existing(self):
        """존재하는 키 삭제"""
        ht = HashTable()
        ht.set("name", "alice")
        assert ht.delete("name") is True
        assert ht.get("name") is None
        assert ht.size() == 0

    def test_delete_nonexistent(self):
        """없는 키 삭제 시 False"""
        ht = HashTable()
        assert ht.delete("ghost") is False

    def test_exists(self):
        """존재 여부 확인"""
        ht = HashTable()
        ht.set("name", "alice")
        assert ht.exists("name") is True
        assert ht.exists("ghost") is False

    def test_keys(self):
        """전체 키 목록"""
        ht = HashTable()
        ht.set("a", "1")
        ht.set("b", "2")
        assert sorted(ht.keys()) == ["a", "b"]

    def test_size(self):
        """항목 수 카운트"""
        ht = HashTable()
        assert ht.size() == 0
        ht.set("a", "1")
        assert ht.size() == 1
        ht.delete("a")
        assert ht.size() == 0

    def test_hash_stays_inside_bucket_range(self):
        """해시 결과는 항상 버킷 범위 안에 있어야 함"""
        ht = HashTable(initial_capacity=8)
        bucket_index = ht._hash("range-check")
        assert 0 <= bucket_index < 8

    def test_collision(self, monkeypatch: pytest.MonkeyPatch):
        """해시 충돌 시 chaining 동작"""
        ht = HashTable(initial_capacity=4)

        # 모든 키가 같은 버킷으로 가게 만들어 충돌 상황을 강제로 만든다.
        monkeypatch.setattr(HashTable, "_hash", lambda self, key: 0)

        ht.set("a", "1")
        ht.set("b", "2")
        ht.set("c", "3")

        assert ht.get("a") == "1"
        assert ht.get("b") == "2"
        assert ht.get("c") == "3"
        assert ht.keys() == ["a", "b", "c"]

    def test_resize(self):
        """load factor 초과 시 resize + 데이터 보존"""
        ht = HashTable(initial_capacity=4, load_factor=0.75)

        for index in range(10):
            ht.set(f"key{index}", f"val{index}")

        assert ht._capacity >= 8
        assert ht.size() == 10
        for index in range(10):
            assert ht.get(f"key{index}") == f"val{index}"

    def test_empty_string_key_and_value(self):
        """빈 문자열도 정상적으로 저장하고 조회할 수 있어야 함"""
        ht = HashTable()
        ht.set("", "")
        assert ht.get("") == ""
        assert ht.exists("") is True

    def test_very_long_string_key(self):
        """아주 긴 키도 저장하고 찾을 수 있어야 함"""
        ht = HashTable()
        long_key = "k" * 10_000
        ht.set(long_key, "value")
        assert ht.get(long_key) == "value"

    def test_special_character_key(self):
        """한글과 이모지가 섞인 키도 처리해야 함"""
        ht = HashTable()
        key = "사용자:😀:서울"
        ht.set(key, "ok")
        assert ht.get(key) == "ok"

    def test_bulk_insert_over_thousand_items(self):
        """대량 삽입 후 모든 값이 유지되어야 함"""
        ht = HashTable(initial_capacity=8)

        for index in range(1_500):
            ht.set(f"key-{index}", f"value-{index}")

        assert ht.size() == 1_500
        assert ht.get("key-0") == "value-0"
        assert ht.get("key-1499") == "value-1499"

    def test_reinsert_after_delete(self):
        """삭제 후 같은 키를 다시 넣을 수 있어야 함"""
        ht = HashTable()
        ht.set("name", "alice")
        assert ht.delete("name") is True
        ht.set("name", "bob")
        assert ht.get("name") == "bob"
        assert ht.size() == 1

    def test_delete_one_item_keeps_other_colliding_items(self, monkeypatch: pytest.MonkeyPatch):
        """같은 버킷 안에서 하나만 삭제해도 다른 항목은 남아야 함"""
        ht = HashTable(initial_capacity=2)
        monkeypatch.setattr(HashTable, "_hash", lambda self, key: 0)

        ht.set("a", "1")
        ht.set("b", "2")

        assert ht.delete("a") is True
        assert ht.get("a") is None
        assert ht.get("b") == "2"

    def test_keys_become_empty_after_all_deletes(self):
        """모든 항목을 지우면 키 목록도 비어야 함"""
        ht = HashTable()
        ht.set("a", "1")
        ht.set("b", "2")
        ht.delete("a")
        ht.delete("b")
        assert ht.keys() == []

    def test_resize_preserves_overwritten_value(self):
        """resize 후에도 마지막으로 덮어쓴 값이 유지되어야 함"""
        ht = HashTable(initial_capacity=2, load_factor=0.5)
        ht.set("name", "alice")
        ht.set("name", "bob")
        ht.set("city", "seoul")
        assert ht.get("name") == "bob"

    def test_invalid_initial_capacity_raises_value_error(self):
        """0 이하 capacity는 허용하지 않음"""
        with pytest.raises(ValueError):
            HashTable(initial_capacity=0)

    def test_invalid_load_factor_raises_value_error(self):
        """0 이하 load factor는 허용하지 않음"""
        with pytest.raises(ValueError):
            HashTable(load_factor=0)
