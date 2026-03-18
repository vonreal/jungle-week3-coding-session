"""
SQLite(디스크)와 Mini Redis(메모리) 조회 속도를 비교하는 벤치마크.

핵심 메시지:
1. 같은 데이터를 반복해서 읽으면 캐시가 매우 유리하다.
2. 매번 다른 데이터를 읽으면 캐시가 별 도움을 못 줄 수 있다.
3. TTL이 짧으면 캐시 효과가 줄어든다.
"""

import json
import os
import sqlite3
import time

from mini_redis.store import MiniRedis


DB_PATH = "benchmark_data.db"


def setup_database(num_products: int = 1000) -> None:
    """
    벤치마크용 SQLite DB를 만들고 더미 상품 데이터를 넣는다.

    비유: 도서관 선반에 책 1000권을 먼저 꽂아 두는 작업이다.
    그래야 벤치마크 중에는 "찾는 시간"만 비교할 수 있다.
    """
    # 매번 같은 조건에서 시작해야 결과가 덜 흔들린다.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL
        )
        """
    )

    # 설명을 조금 길게 넣어야 실제 서비스 데이터처럼 덩치가 생긴다.
    categories = ["전자기기", "의류", "식품", "도서", "가구"]
    products: list[tuple[int, str, float, str, str]] = []
    for product_id in range(1, num_products + 1):
        products.append(
            (
                product_id,
                f"상품_{product_id}",
                round(1000 + (product_id * 7.3 % 50000), 2),
                f"이것은 상품 {product_id}번의 상세 설명입니다. " * 5,
                categories[product_id % len(categories)],
            )
        )

    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", products)
    conn.commit()
    conn.close()


def query_from_db(product_id: int) -> str:
    """
    SQLite에서 상품 1건을 조회하고 JSON 문자열로 바꾼다.

    비유: 도서관 서고까지 걸어가서 책 한 권을 찾아와
    요약 카드로 옮겨 적는 과정이다.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 한 번에 상품 하나를 읽는다. 이 과정이 디스크 I/O에 해당한다.
    cursor.execute(
        """
        SELECT id, name, price, description, category
        FROM products
        WHERE id = ?
        """,
        (product_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Product not found: {product_id}")

    return json.dumps(
        {
            "id": row[0],
            "name": row[1],
            "price": row[2],
            "description": row[3],
            "category": row[4],
        },
        ensure_ascii=False,
    )


def _timing_result(total_ms: float, ops: int) -> dict[str, float | int]:
    """
    총 시간과 평균 시간을 같은 형식으로 묶어 돌려준다.

    왜 따로 두는가? 세 시나리오가 같은 구조를 쓰면
    대시보드와 비교 코드가 단순해지기 때문이다.
    """
    return {
        "total_ms": round(total_ms, 3),
        "avg_ms": round(total_ms / ops, 3),
        "ops": ops,
    }


def run_scenario_1(store: MiniRedis, iterations: int = 100) -> dict:
    """
    시나리오 1: 같은 상품을 계속 읽는 경우를 측정한다.

    이 상황은 인기 상품 상세 페이지처럼
    같은 데이터가 반복 조회될 때 캐시가 얼마나 강한지 보여준다.
    """
    store.flush()
    product_id = 42
    cache_key = f"product:{product_id}"

    # 기준선은 "캐시 없이 매번 DB에서 읽는 시간"이다.
    db_only_start = time.perf_counter()
    for _ in range(iterations):
        query_from_db(product_id)
    db_only_total_ms = (time.perf_counter() - db_only_start) * 1000

    cache_hits = 0
    cache_misses = 0

    # 캐시 경로는 첫 요청만 DB를 쓰고, 그 뒤에는 메모리에서 읽는다.
    with_cache_start = time.perf_counter()
    for _ in range(iterations):
        cached_value = store.get(cache_key)
        if cached_value is None:
            cache_misses += 1
            cached_value = query_from_db(product_id)
            store.set(cache_key, cached_value)
        else:
            cache_hits += 1
    with_cache_total_ms = (time.perf_counter() - with_cache_start) * 1000

    safe_with_cache_total_ms = max(with_cache_total_ms, 0.001)
    return {
        "title": "같은 데이터 반복 조회 (캐시 유효)",
        "db_only": _timing_result(db_only_total_ms, iterations),
        "with_cache": {
            **_timing_result(with_cache_total_ms, iterations),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        },
        "speedup": round(db_only_total_ms / safe_with_cache_total_ms, 2),
    }


def run_scenario_2(store: MiniRedis, iterations: int = 100) -> dict:
    """
    시나리오 2: 매번 다른 상품을 읽는 경우를 측정한다.

    이 상황은 검색 결과처럼 요청이 계속 바뀌어
    캐시가 적중하지 못하는 장면을 보여준다.
    """
    store.flush()

    db_only_start = time.perf_counter()
    for product_id in range(1, iterations + 1):
        query_from_db(product_id)
    db_only_total_ms = (time.perf_counter() - db_only_start) * 1000

    cache_hits = 0
    cache_misses = 0

    # 모든 요청이 다르면 캐시는 거의 장부만 쓰고 끝난다.
    with_cache_start = time.perf_counter()
    for product_id in range(1, iterations + 1):
        cache_key = f"product:{product_id}"
        cached_value = store.get(cache_key)
        if cached_value is None:
            cache_misses += 1
            cached_value = query_from_db(product_id)
            store.set(cache_key, cached_value)
        else:
            cache_hits += 1
    with_cache_total_ms = (time.perf_counter() - with_cache_start) * 1000

    safe_with_cache_total_ms = max(with_cache_total_ms, 0.001)
    return {
        "title": "매번 다른 데이터 조회 (캐시 무효)",
        "db_only": _timing_result(db_only_total_ms, iterations),
        "with_cache": {
            **_timing_result(with_cache_total_ms, iterations),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        },
        "speedup": round(db_only_total_ms / safe_with_cache_total_ms, 2),
    }


def run_scenario_3(store: MiniRedis, iterations: int = 100) -> dict:
    """
    시나리오 3: 같은 상품을 읽지만 TTL이 매우 짧은 경우를 측정한다.

    이 상황은 자주 바뀌는 랭킹 데이터처럼
    캐시가 도움이 되지만 오래 유지되지는 못하는 장면에 가깝다.
    """
    store.flush()
    product_id = 42
    cache_key = f"product:{product_id}"

    # 비교를 공정하게 하려고 DB 쪽도 같은 요청 간격으로 측정한다.
    db_only_start = time.perf_counter()
    for _ in range(iterations):
        query_from_db(product_id)
        time.sleep(0.05)
    db_only_total_ms = (time.perf_counter() - db_only_start) * 1000

    cache_hits = 0
    cache_misses = 0

    # TTL=1초로 두면 반복 조회 중간에 캐시가 여러 번 만료된다.
    with_cache_start = time.perf_counter()
    for _ in range(iterations):
        cached_value = store.get(cache_key)
        if cached_value is None:
            cache_misses += 1
            cached_value = query_from_db(product_id)
            store.set(cache_key, cached_value, ttl=1)
        else:
            cache_hits += 1
        time.sleep(0.05)
    with_cache_total_ms = (time.perf_counter() - with_cache_start) * 1000

    safe_with_cache_total_ms = max(with_cache_total_ms, 0.001)
    return {
        "title": "짧은 TTL로 반복 조회 (캐시 부분 유효)",
        "db_only": _timing_result(db_only_total_ms, iterations),
        "with_cache": {
            **_timing_result(with_cache_total_ms, iterations),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        },
        "speedup": round(db_only_total_ms / safe_with_cache_total_ms, 2),
    }


def run_benchmark(iterations: int = 100) -> dict:
    """
    전체 벤치마크를 한 번에 실행한다.

    순서:
    1. SQLite 더미 DB 준비
    2. MiniRedis 준비
    3. 세 시나리오 실행
    4. 자원 정리
    """
    setup_database()
    store = MiniRedis()

    try:
        return {
            "scenario_1_repeated_reads": run_scenario_1(store, iterations),
            "scenario_2_unique_reads": run_scenario_2(store, iterations),
            "scenario_3_short_ttl": run_scenario_3(store, iterations),
        }
    finally:
        # 백그라운드 정리 스레드와 테스트용 DB 파일을 함께 정리한다.
        store.shutdown()
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result, indent=2, ensure_ascii=False))
