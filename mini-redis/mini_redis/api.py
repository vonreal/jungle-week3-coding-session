from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mini_redis.store import MiniRedis


app = FastAPI(title="Mini Redis", version="0.1.0")
store = MiniRedis()


class SetRequest(BaseModel):
    key: str
    value: str
    ttl: int | None = None


@app.post("/set")
def set_key(req: SetRequest):
    """키-값 저장"""
    raise NotImplementedError


@app.get("/get/{key}")
def get_key(key: str):
    """키 조회"""
    raise NotImplementedError


@app.delete("/del/{key}")
def delete_key(key: str):
    """키 삭제"""
    raise NotImplementedError


@app.get("/keys")
def list_keys():
    """저장된 키 목록 + 각 키의 TTL 잔여시간"""
    raise NotImplementedError


@app.post("/run-tests")
def run_tests():
    """pytest 실행 후 결과 반환 (대시보드용)"""
    raise NotImplementedError


@app.get("/info")
def get_info():
    """저장소 상태 정보"""
    raise NotImplementedError


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """대시보드 HTML 서빙"""
    raise NotImplementedError


@app.on_event("shutdown")
def shutdown_event():
    """서버 종료 시 백그라운드 스레드 정리"""
    store.shutdown()

