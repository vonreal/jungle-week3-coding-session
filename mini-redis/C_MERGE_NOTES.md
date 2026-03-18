# C Merge Notes

## Purpose

이 파일은 C 담당 통합 체크용 임시 메모다.
B의 `store.py`가 머지된 뒤 이 파일을 참고해서 fallback 코드를 제거하고,
최종 통합 테스트를 끝내면 이 파일도 함께 삭제한다.

## Current Temporary Code

아래 코드는 A/B 구현이 아직 합쳐지기 전이라 넣어둔 임시 장치다.

- `mini_redis/api.py`
  - `_ApiFallbackStore`
  - `_build_store()`
  - `store = _build_store()`
- `benchmark.py`
  - `_BenchmarkFallbackStore`
  - `_build_store()`
  - `store = _build_store()` inside benchmark flow

## Merge Order Reminder

1. A가 `feature/hashtable` 완료
2. B가 A를 머지하고 `store.py` 통합 및 테스트 확인
3. C가 B 결과를 머지하고 API 전체 통합 테스트 수행

## After B Merge

### 1. Remove temporary fallback code

- `mini_redis/api.py`
  - `_ApiFallbackStore` 삭제
  - `_build_store()` 삭제
  - `store = MiniRedis()`로 변경
- `benchmark.py`
  - `_BenchmarkFallbackStore` 삭제
  - `_build_store()` 삭제
  - 실제 `MiniRedis()`만 사용하도록 단순화

### 2. Re-test integration

- `PYTHONPATH=. .venv/bin/pytest -q`
- `PYTHONPATH=. .venv/bin/python -c "from mini_redis.api import app; print(app.title)"`
- `uvicorn mini_redis.api:app --host 127.0.0.1 --port 8000`
- `/docs` 확인
- `/dashboard` 확인
- TTL 실제 만료 확인
- `/run-benchmark` 확인

### 3. Final cleanup

- 이 파일 `C_MERGE_NOTES.md` 삭제
- 관련 정리 커밋 생성

## What C Should Be Ready To Explain

- FastAPI 요청 흐름
  - Request -> Pydantic -> endpoint -> store -> response
- 왜 400/404/500으로 나눴는지
- `/run-tests`를 subprocess로 돌린 이유
- 대시보드가 fetch로 API를 호출하는 흐름
- fallback을 왜 잠깐 넣었고, 언제 제거하는지
