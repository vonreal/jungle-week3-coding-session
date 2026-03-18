class HashTable:
    """
    해시 테이블 직접 구현 (파이썬 dict 사용 금지)
    - 내부: 고정 크기 배열(list) + chaining(연결 리스트 또는 list of lists)
    - 해시 함수: 파이썬 내장 hash() 사용 가능
    - load factor 초과 시 동적 resize
    """

    def __init__(self, initial_capacity: int = 16, load_factor: float = 0.75):
        raise NotImplementedError

    def set(self, key: str, value: str) -> None:
        """키-값 저장. 이미 존재하면 덮어쓰기"""
        raise NotImplementedError

    def get(self, key: str) -> str | None:
        """키 조회. 없으면 None"""
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        """키 삭제. 성공 True, 없으면 False"""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """키 존재 여부"""
        raise NotImplementedError

    def keys(self) -> list[str]:
        """모든 키 목록 반환"""
        raise NotImplementedError

    def size(self) -> int:
        """저장된 항목 수"""
        raise NotImplementedError

    def _hash(self, key: str) -> int:
        """해시 함수 — 키를 bucket 인덱스로 변환"""
        raise NotImplementedError

    def _resize(self) -> None:
        """capacity 2배 확장 후 전체 재해싱"""
        raise NotImplementedError

