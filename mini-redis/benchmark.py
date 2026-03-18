"""
캐시 유/무 성능 비교.

시나리오:
1. "무거운 연산" 시뮬레이션
2. 캐시 없이 N번 반복 실행
3. 캐시에 한 번 저장한 뒤 N번 반복 실행
4. 결과를 JSON으로 출력
"""

import json
import time

from mini_redis.store import MiniRedis


class _BenchmarkFallbackStore:
    """
    벤치마크용 임시 캐시 저장소.

    비유: 정식 창고가 없을 때 잠깐 쓰는 메모 상자다.
    왜 필요한가? B 담당의 MiniRedis가 아직 비어 있어도
    C 담당은 벤치마크 흐름을 먼저 완성할 수 있어야 하기 때문이다.
    """

    def __init__(self):
        """간단한 키-값 저장 상자를 만든다."""
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """키가 있으면 값을 돌려주고, 없으면 None을 돌려준다."""
        return self._values.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """
        값을 저장한다.

        ttl은 실제 MiniRedis와 인터페이스를 맞추기 위해 받지만,
        벤치마크에서는 만료 기능이 핵심이 아니라서 사용하지 않는다.
        """
        self._values[key] = value

    def shutdown(self) -> None:
        """임시 저장소는 따로 정리할 자원이 없어서 그대로 끝낸다."""
        return None


def _build_store():
    """
    진짜 MiniRedis를 만들 수 있으면 쓰고, 아니면 임시 저장소를 쓴다.

    왜 필요한가? A/B 작업이 끝나기 전에도 C 담당이 성능 비교 화면을 만들 수 있어야 하기 때문이다.
    """
    try:
        return MiniRedis()
    except NotImplementedError:
        return _BenchmarkFallbackStore()


def heavy_computation(n: int) -> str:
    """
    무거운 연산을 흉내 내는 함수.

    비유: 계산기 대신 손으로 긴 계산을 여러 번 해보는 상황이다.
    왜 필요한가? 캐시가 없을 때와 있을 때의 시간 차이를 눈에 띄게 만들기 위해서다.
    """
    # 반복 횟수를 늘려서 "한 번 계산할 때 꽤 오래 걸리는 일"처럼 만든다.
    a, b = 0, 1
    limit = max(1, n) * 6000

    # 피보나치 비슷한 계산을 반복해 CPU 일을 조금 시킨다.
    for _ in range(limit):
        a, b = b, (a + b) % 1000000007

    # 아주 짧은 sleep도 섞어서 캐시 효과가 더 또렷하게 보이게 한다.
    time.sleep(0.002)
    return f"fib:{n}:{a}"


def run_benchmark(iterations: int = 100) -> dict:
    """
    캐시 유무 성능 비교를 실행한다.

    흐름:
    1. 같은 입력으로 무거운 연산을 여러 번 반복한다.
    2. 캐시 없이 걸린 시간을 잰다.
    3. 캐시에 한 번 저장한 뒤 다시 시간을 잰다.
    4. 평균 시간과 속도 향상 배수를 계산한다.
    """
    store = _build_store()
    input_number = 32
    cache_key = f"benchmark:{input_number}"

    # 먼저 캐시 없이 같은 계산을 계속 반복한다.
    no_cache_start = time.perf_counter()
    for _ in range(iterations):
        heavy_computation(input_number)
    no_cache_total_ms = (time.perf_counter() - no_cache_start) * 1000

    # 다음에는 첫 계산 결과를 저장하고 나머지는 캐시에서 꺼낸다.
    with_cache_start = time.perf_counter()
    for _ in range(iterations):
        cached_value = store.get(cache_key)
        if cached_value is None:
            cached_value = heavy_computation(input_number)
            store.set(cache_key, cached_value)
    with_cache_total_ms = (time.perf_counter() - with_cache_start) * 1000

    # 분모가 0이 되는 일을 막기 위해 아주 작은 최소값을 둔다.
    safe_with_cache_total_ms = max(with_cache_total_ms, 0.001)
    result = {
        "without_cache": {
            "total_ms": round(no_cache_total_ms, 3),
            "avg_ms": round(no_cache_total_ms / iterations, 3),
            "ops": iterations,
        },
        "with_cache": {
            "total_ms": round(with_cache_total_ms, 3),
            "avg_ms": round(with_cache_total_ms / iterations, 3),
            "ops": iterations,
        },
        "speedup": round(no_cache_total_ms / safe_with_cache_total_ms, 3),
    }

    # MiniRedis가 백그라운드 자원을 쓴다면 마지막에 정리한다.
    store.shutdown()
    return result


if __name__ == "__main__":
    # 스크립트로 직접 실행하면 사람이 읽기 좋은 JSON으로 출력한다.
    result = run_benchmark()
    print(json.dumps(result, indent=2))
