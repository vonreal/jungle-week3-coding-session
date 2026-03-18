import threading
import time

from mini_redis.hashtable import HashTable


class MiniRedis:
    """
    HashTable 위에 동시성(Lock)과 TTL을 추가한 래퍼.
    - threading.RLock으로 모든 읽기/쓰기를 감쌈
    - TTL: 별도 dict에 {key: expire_timestamp} 저장
    - lazy expiry: get 시 만료 체크
    - periodic expiry: 백그라운드 스레드가 주기적으로 만료 키 정리
    """

    def __init__(self, cleanup_interval: float = 1.0):
        raise NotImplementedError

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """
        키-값 저장.
        ttl: 초 단위 만료 시간. None이면 만료 없음.
        """
        raise NotImplementedError

    def get(self, key: str) -> str | None:
        """키 조회. 만료된 키는 삭제 후 None 반환 (lazy expiry)"""
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        """키 삭제"""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """키 존재 여부 (만료 체크 포함)"""
        raise NotImplementedError

    def keys(self) -> list[str]:
        """만료되지 않은 모든 키 목록"""
        raise NotImplementedError

    def ttl(self, key: str) -> int | None:
        """남은 TTL(초). 만료 없으면 None, 키 없으면 -1"""
        raise NotImplementedError

    def invalidate(self, key: str) -> bool:
        """키를 즉시 무효화 (삭제와 동일하지만 의미적 구분)"""
        raise NotImplementedError

    def flush(self) -> None:
        """모든 데이터 삭제"""
        raise NotImplementedError

    def info(self) -> dict:
        """저장소 상태 정보 (총 키 수, 만료 대기 수 등)"""
        raise NotImplementedError

    def _cleanup_expired(self) -> None:
        """백그라운드 스레드: 주기적으로 만료된 키 정리"""
        raise NotImplementedError

    def shutdown(self) -> None:
        """백그라운드 스레드 정리 종료"""
        raise NotImplementedError

