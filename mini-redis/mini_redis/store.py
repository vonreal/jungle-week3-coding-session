import threading
import time
import math

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
        """
        저장소의 기본 부품을 준비하는 함수.

        비유하면 작은 창고를 열기 전에
        선반(HashTable), 유통기한 표(_expiry), 자물쇠(RLock),
        그리고 청소부 스레드를 준비하는 단계다.
        이렇게 미리 준비해야 여러 스레드가 동시에 와도 안전하게 일할 수 있다.
        """
        # 실제 데이터는 A가 만든 해시 테이블에 넣는다.
        self._data = HashTable()
        # TTL 정보는 보조 장부처럼 따로 적어 둔다.
        self._expiry: dict[str, float] = {}
        # 같은 스레드가 다시 들어와도 멈추지 않게 RLock을 쓴다.
        self._lock = threading.RLock()
        # 청소부 스레드가 얼마나 자주 돌지 저장한다.
        self._cleanup_interval = cleanup_interval
        # shutdown() 전까지 청소부가 계속 돌도록 깃발을 켠다.
        self._running = True
        # 주기적으로 만료 키를 치우는 배경 스레드를 만든다.
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_expired,
            daemon=True,
        )
        self._cleanup_thread.start()

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """
        키-값 저장.
        ttl: 초 단위 만료 시간. None이면 만료 없음.
        """
        # 쓰기 작업은 항상 자물쇠를 잠그고 한다.
        with self._lock:
            # 먼저 실제 값을 저장한다.
            self._data.set(key, value)
            # ttl이 있으면 지금 시각에 ttl초를 더해 유통기한을 적는다.
            if ttl is not None:
                self._expiry[key] = time.time() + ttl
            else:
                # ttl이 없으면 예전 유통기한 기록을 지워 영구 보관으로 바꾼다.
                self._expiry.pop(key, None)

    def get(self, key: str) -> str | None:
        """
        키로 값을 찾아오는 함수.

        값을 바로 꺼내지 않고, 먼저 유통기한이 지났는지 확인한다.
        편의점에서 음료를 집기 전에 날짜를 먼저 보는 것과 같다.
        만료됐으면 치우고 None을 돌려주고,
        아직 괜찮으면 저장된 값을 돌려준다.
        """
        with self._lock:
            # 누가 찾으러 왔을 때만 검사하는 lazy expiry를 적용한다.
            if self._purge_if_expired(key):
                return None
            return self._data.get(key)

    def delete(self, key: str) -> bool:
        """
        키를 저장소에서 지우는 함수.

        진열대의 상품과 유통기한 메모를 같이 치워야
        나중에 오래된 기록이 남지 않는다.
        """
        with self._lock:
            # TTL 장부의 흔적도 같이 지운다.
            self._expiry.pop(key, None)
            return self._data.delete(key)

    def exists(self, key: str) -> bool:
        """
        키가 아직 살아 있는지 확인하는 함수.

        이름표가 있다고 끝이 아니라,
        유통기한이 지났는지도 같이 봐야 진짜 존재 여부를 알 수 있다.
        """
        with self._lock:
            if self._purge_if_expired(key):
                return False
            return self._data.exists(key)

    def keys(self) -> list[str]:
        """
        아직 사용할 수 있는 키 목록을 돌려주는 함수.

        먼저 만료된 키를 청소한 뒤 목록을 꺼내야
        사용자가 오래된 키를 보지 않게 된다.
        """
        with self._lock:
            self._purge_all_expired()
            return self._data.keys()

    def ttl(self, key: str) -> int | None:
        """
        키의 남은 TTL을 알려주는 함수.

        만료 시간이 없는 물건은 None,
        아예 없는 물건은 -1을 돌려준다.
        TTL이 있으면 남은 시간을 올림해서 정수 초로 보여 준다.
        """
        with self._lock:
            if self._purge_if_expired(key):
                return -1
            if not self._data.exists(key):
                return -1
            if key not in self._expiry:
                return None
            # 아주 조금 남았어도 0초로 보이지 않게 올림을 쓴다.
            remaining = self._expiry[key] - time.time()
            return max(0, math.ceil(remaining))

    def invalidate(self, key: str) -> bool:
        """
        키를 즉시 무효로 만드는 함수.

        동작은 delete와 같지만,
        읽는 사람에게 '강제로 만료시켰다'는 뜻을 더 분명히 보여 준다.
        """
        with self._lock:
            return self.delete(key)

    def flush(self) -> None:
        """
        저장소를 통째로 비우는 함수.

        창고 대청소처럼 모든 키와 TTL 정보를 함께 비워야
        상태가 깔끔하게 초기화된다.
        """
        with self._lock:
            # 키 목록을 먼저 복사해서 돌면 삭제 중 목록이 흔들려도 안전하다.
            for key in list(self._data.keys()):
                self._data.delete(key)
            self._expiry.clear()

    def info(self) -> dict:
        """
        저장소의 현재 상태를 요약해 주는 함수.

        오래된 키를 먼저 치운 뒤 숫자를 세야
        창고 재고표가 실제 상태와 맞아 떨어진다.
        """
        with self._lock:
            self._purge_all_expired()
            total_keys = self._data.size()
            keys_with_ttl = len(self._expiry)
            return {
                "total_keys": total_keys,
                "keys_with_ttl": keys_with_ttl,
                "keys_without_ttl": total_keys - keys_with_ttl,
            }

    def _is_expired(self, key: str) -> bool:
        """
        키의 유통기한이 지났는지 확인하는 함수.

        TTL 기록이 없으면 만료 대상이 아니므로 False다.
        """
        expire_at = self._expiry.get(key)
        if expire_at is None:
            return False
        return expire_at <= time.time()

    def _purge_if_expired(self, key: str) -> bool:
        """
        키 하나가 만료됐으면 바로 치우는 내부 함수.

        검사와 삭제를 묶어 두면 get, exists, ttl 같은 여러 함수가
        같은 규칙을 재사용할 수 있어 실수가 줄어든다.
        """
        if not self._is_expired(key):
            return False
        self._data.delete(key)
        self._expiry.pop(key, None)
        return True

    def _purge_all_expired(self) -> None:
        """
        만료된 키를 한 번에 정리하는 내부 함수.

        keys()나 info()처럼 전체 상태를 보여 줄 때는
        먼저 이 정리를 해야 낡은 데이터가 섞이지 않는다.
        """
        expired_keys = [key for key in self._expiry if self._is_expired(key)]
        for key in expired_keys:
            self._data.delete(key)
            self._expiry.pop(key, None)

    def _cleanup_expired(self) -> None:
        """
        백그라운드 청소부 함수.

        손님이 찾지 않아도 일정 시간마다 창고를 돌면서
        만료된 물건을 치워 두기 위해 계속 반복 실행한다.
        """
        while self._running:
            # 너무 바쁘게 돌면 CPU를 낭비하니 잠깐 쉰다.
            time.sleep(self._cleanup_interval)
            # 정리 작업도 다른 읽기/쓰기와 충돌하지 않게 잠그고 한다.
            with self._lock:
                self._purge_all_expired()

    def shutdown(self) -> None:
        """
        백그라운드 청소부를 안전하게 멈추는 함수.

        프로그램이 끝날 때 정리하지 않으면
        테스트나 서버 종료 시 배경 스레드가 남아 혼란을 만들 수 있다.
        """
        # 먼저 반복 루프를 끝내라고 신호를 보낸다.
        self._running = False
        # 자기 자신을 join하면 멈춰 버리므로 그 경우는 피한다.
        if (
            self._cleanup_thread.is_alive()
            and threading.current_thread() is not self._cleanup_thread
        ):
            self._cleanup_thread.join()
