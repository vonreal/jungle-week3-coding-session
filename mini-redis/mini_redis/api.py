import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mini_redis.store import MiniRedis


class _ApiFallbackStore:
    """
    API 작업을 잠시 막지 않기 위한 임시 저장소.

    비유: 아직 진짜 창고(MiniRedis)가 완성되지 않았을 때,
    임시 선반에 물건을 올려두는 상태다.
    왜 필요한가? B 담당의 store 구현이 아직 stub이면
    api.py를 import하는 순간 바로 멈추기 때문이다.
    """

    def __init__(self):
        """
        임시 저장 공간과 TTL 표를 만든다.

        values는 "키에 어떤 값이 들어 있는지" 적어두는 칸이고,
        expiries는 "언제 치워야 하는지" 적어두는 메모장이다.
        """
        self._values: dict[str, str] = {}
        self._expiries: dict[str, float] = {}
        self._lock = threading.RLock()

    def _purge_expired_key(self, key: str, now: float | None = None) -> None:
        """
        한 키가 만료됐는지 보고, 시간이 다 됐으면 바로 치운다.

        비유: 유통기한 지난 도시락을 발견하면 냉장고에서 바로 빼는 것.
        왜 필요한가? get, keys, info가 오래된 데이터를 보여주면 안 되기 때문이다.
        """
        current_time = time.time() if now is None else now

        # 만료 시간이 적혀 있지 않으면 치울 필요가 없다.
        expire_at = self._expiries.get(key)
        if expire_at is None:
            return

        # 유통기한이 지났으면 값과 TTL 메모를 함께 지운다.
        if expire_at <= current_time:
            self._values.pop(key, None)
            self._expiries.pop(key, None)

    def _purge_all_expired(self) -> None:
        """
        저장된 키를 한 바퀴 돌며 만료된 것을 정리한다.

        비유: 가게 마감 전에 선반을 한 번 쭉 보며
        상한 물건을 치우는 점검 시간이다.
        """
        now = time.time()

        # list(...)로 복사해 두면, 순회 중 삭제해도 안전하다.
        for key in list(self._values.keys()):
            self._purge_expired_key(key, now)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """
        값을 저장하고, TTL이 있으면 만료 시간도 함께 적어둔다.

        비유: 사물함에 물건을 넣고, "몇 초 뒤 비워" 메모를 붙이는 것.
        """
        with self._lock:
            # 먼저 값을 저장한다.
            self._values[key] = value

            # TTL이 있으면 만료 시각을 계산해 기록한다.
            if ttl is not None:
                self._expiries[key] = time.time() + ttl
            else:
                self._expiries.pop(key, None)

    def get(self, key: str) -> str | None:
        """
        값을 읽기 전에 만료 여부를 먼저 확인한다.

        비유: 사물함을 열기 전에 "이미 정리 시간이 지났나?"를 확인하는 것.
        """
        with self._lock:
            # 오래된 값이면 먼저 치운 뒤 None을 돌려준다.
            self._purge_expired_key(key)
            return self._values.get(key)

    def delete(self, key: str) -> bool:
        """
        키를 지우고, 실제로 지운 것이 있으면 True를 돌려준다.

        왜 필요한가? API가 "정말 지웠는지" 사용자에게 알려주기 위해서다.
        """
        with self._lock:
            existed = key in self._values

            # 값과 TTL 메모를 함께 지워야 찌꺼기가 남지 않는다.
            self._values.pop(key, None)
            self._expiries.pop(key, None)
            return existed

    def exists(self, key: str) -> bool:
        """
        키가 살아 있는지 확인한다.

        비유: 이름표가 아직 선반에 붙어 있는지 보는 것.
        """
        with self._lock:
            self._purge_expired_key(key)
            return key in self._values

    def keys(self) -> list[str]:
        """
        아직 만료되지 않은 키 목록을 돌려준다.

        왜 필요한가? 대시보드가 현재 어떤 데이터가 남아 있는지 보여줘야 하기 때문이다.
        """
        with self._lock:
            self._purge_all_expired()
            return sorted(self._values.keys())

    def ttl(self, key: str) -> int | None:
        """
        남은 TTL을 초 단위로 계산해 돌려준다.

        규칙:
        - 키가 없으면 -1
        - 만료가 없으면 None
        - 만료가 있으면 남은 초(int)
        """
        with self._lock:
            self._purge_expired_key(key)

            # 값 자체가 없으면 없는 키다.
            if key not in self._values:
                return -1

            # 만료 메모가 없으면 무기한 저장 상태다.
            expire_at = self._expiries.get(key)
            if expire_at is None:
                return None

            # ceil을 쓰면 막 저장한 TTL이 바로 59로 줄어 보이지 않는다.
            remaining = max(0, math.ceil(expire_at - time.time()))
            return remaining

    def invalidate(self, key: str) -> bool:
        """
        의미상 "무효화"지만 실제 동작은 삭제와 같다.

        왜 따로 두는가? 나중에 API나 로직에서 "삭제"와 "강제 무효화"를
        말로 구분하고 싶을 수 있기 때문이다.
        """
        return self.delete(key)

    def flush(self) -> None:
        """
        저장된 모든 값을 비운다.

        비유: 서랍 전체를 한 번에 비우는 초기화 버튼이다.
        """
        with self._lock:
            self._values.clear()
            self._expiries.clear()

    def info(self) -> dict[str, int]:
        """
        현재 저장소 상태를 숫자로 요약한다.

        왜 필요한가? 대시보드가 "지금 몇 개 저장됐는지" 한눈에 보여주기 위해서다.
        """
        with self._lock:
            self._purge_all_expired()
            total_keys = len(self._values)
            keys_with_ttl = len(self._expiries)
            return {
                "total_keys": total_keys,
                "keys_with_ttl": keys_with_ttl,
                "keys_without_ttl": total_keys - keys_with_ttl,
            }

    def shutdown(self) -> None:
        """
        임시 저장소는 백그라운드 스레드가 없어서 정리할 것이 거의 없다.

        왜 메서드가 필요한가? 진짜 MiniRedis와 같은 인터페이스를 맞추기 위해서다.
        """
        return None


def _build_store() -> Any:
    """
    가능한 경우 진짜 MiniRedis를 만들고, 아직 stub이면 임시 저장소를 쓴다.

    비유: 정식 창고 문이 열려 있으면 그쪽으로 가고,
    아직 공사 중이면 임시 선반을 쓰는 분기점이다.
    """
    try:
        return MiniRedis()
    except NotImplementedError:
        # 아직 B 담당 구현이 비어 있으면 API 작업이 멈추지 않게 임시 저장소를 쓴다.
        return _ApiFallbackStore()


app = FastAPI(title="Mini Redis", version="0.1.0")
store = _build_store()


class SetRequest(BaseModel):
    """SET 요청에서 받는 입력 형식."""

    key: str
    value: str
    ttl: int | None = None


class SetResponse(BaseModel):
    """SET 요청이 성공했을 때 돌려주는 형식."""

    status: str
    key: str


class GetResponse(BaseModel):
    """GET 요청이 성공했을 때 돌려주는 형식."""

    key: str
    value: str


class DeleteResponse(BaseModel):
    """DELETE 요청 결과를 알려주는 형식."""

    status: str
    key: str
    deleted: bool


class KeyInfo(BaseModel):
    """키 목록 화면에 보여줄 key + ttl 묶음."""

    key: str
    ttl: int | None


@app.post("/set", response_model=SetResponse)
def set_key(req: SetRequest):
    """
    키-값을 저장하는 API.

    비유: 사물함 번호(key)를 정하고 물건(value)을 넣는 버튼이다.
    ttl이 있으면 "몇 초 뒤 자동으로 치워줘"라고 함께 적는 셈이다.
    왜 필요한가? 사용자가 REST API로 데이터를 넣는 가장 기본 동작이기 때문이다.
    """
    # 빈 키는 허용하지 않는다. 이름표 없는 사물함은 찾을 수 없기 때문이다.
    if req.key == "":
        raise HTTPException(status_code=400, detail="Key cannot be empty")

    try:
        # 저장소에 값을 넣는다.
        store.set(req.key, req.value, req.ttl)
        return SetResponse(status="OK", key=req.key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to set key: {exc}") from exc


@app.get("/get/{key}", response_model=GetResponse)
def get_key(key: str):
    """
    키에 들어 있는 값을 읽는 API.

    비유: 사물함 번호를 입력하고 안에 든 물건을 확인하는 버튼이다.
    왜 필요한가? 저장이 제대로 됐는지, 현재 값이 무엇인지 바로 확인해야 하기 때문이다.
    """
    try:
        # 저장소에서 값을 읽는다.
        value = store.get(key)

        # 값이 없으면 404로 알려준다.
        if value is None:
            raise HTTPException(status_code=404, detail="Key not found")

        return GetResponse(key=key, value=value)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get key: {exc}") from exc


@app.delete("/del/{key}", response_model=DeleteResponse)
def delete_key(key: str):
    """
    키를 삭제하는 API.

    비유: 사물함을 비우는 버튼이다.
    왜 필요한가? 테스트와 대시보드에서 불필요한 데이터를 치워야 하기 때문이다.
    """
    try:
        # 삭제 성공 여부를 함께 돌려준다.
        deleted = store.delete(key)
        return DeleteResponse(status="OK", key=key, deleted=deleted)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete key: {exc}") from exc


@app.get("/keys", response_model=list[KeyInfo])
def list_keys():
    """
    현재 저장된 키 목록과 TTL을 보여주는 API.

    비유: 사물함 복도 전체를 훑어보며,
    "어떤 칸이 차 있는지"와 "언제 비워질지"를 표로 적어 보여주는 기능이다.
    """
    try:
        items: list[KeyInfo] = []

        # 먼저 키 목록을 가져온 뒤, 각 키의 TTL을 하나씩 붙인다.
        for key in store.keys():
            ttl_value = store.ttl(key)

            # 순회 중 막 만료됐으면 목록에서 건너뛴다.
            if ttl_value == -1:
                continue

            items.append(KeyInfo(key=key, ttl=ttl_value))

        return items
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list keys: {exc}") from exc


@app.get("/info")
def get_info():
    """
    저장소 상태를 숫자로 요약해서 보여주는 API.

    왜 필요한가? 총 키 개수, TTL 있는 키 개수 같은 정보를
    대시보드 상단에서 바로 보여주면 현재 상태를 빠르게 파악할 수 있기 때문이다.
    """
    try:
        return store.info()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get info: {exc}") from exc


@app.post("/flush")
def flush_all():
    """
    모든 데이터를 한 번에 비우는 API.

    비유: 칠판을 지우개로 한 번에 깨끗하게 지우는 버튼이다.
    왜 필요한가? 데모나 테스트를 새 상태에서 다시 시작하기 쉽도록 하기 위해서다.
    """
    try:
        # 저장소 전체를 초기화한다.
        store.flush()
        return {"status": "OK", "message": "All keys flushed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to flush keys: {exc}") from exc


@app.post("/run-tests")
def run_tests():
    """
    pytest를 별도 프로세스로 실행하고 결과를 돌려주는 API.

    비유: "시험 채점" 버튼을 누르면,
    서버 바깥에서 채점기를 따로 돌려 결과표만 받아오는 방식이다.
    왜 별도 프로세스를 쓰는가? 테스트가 서버의 현재 메모리 상태를 망치지 않게 하려는 안전장치다.
    """
    project_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()

    # 중첩 pytest가 또 /run-tests를 부르며 끝없이 늘어나는 일을 막기 위한 표식이다.
    env["MINI_REDIS_SKIP_NESTED_RUN_TESTS"] = "1"

    try:
        # 현재 파이썬 실행 파일로 pytest를 호출하면 가상환경을 더 안정적으로 따라간다.
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=short", "-q"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=project_root,
            env=env,
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False,
            "output": exc.stdout or "",
            "errors": "Pytest timed out after 30 seconds",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run tests: {exc}") from exc


@app.post("/run-benchmark")
def run_benchmark():
    """
    캐시 유무 성능 비교를 실행하는 API.

    왜 필요한가? 대시보드에서 버튼 한 번으로
    "캐시를 썼을 때 얼마나 빨라지는지" 바로 보여주기 위해서다.
    """
    try:
        # 함수 안에서 import하면 서버 시작 시점의 부담과 순환 참조 위험을 줄일 수 있다.
        from benchmark import run_benchmark as execute_benchmark

        return execute_benchmark()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run benchmark: {exc}") from exc


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """
    대시보드 HTML 파일을 읽어서 그대로 보여주는 API.

    비유: 완성된 안내판 한 장을 브라우저에 그대로 걸어주는 것이다.
    왜 파일로 두는가? 프론트엔드 프로젝트를 따로 만들지 않고 한 파일로 관리하기 쉽기 때문이다.
    """
    dashboard_path = Path(__file__).parent / "dashboard.html"

    try:
        # 파일 내용을 UTF-8로 읽어 브라우저에 HTML로 내려준다.
        return dashboard_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dashboard file not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {exc}") from exc


@app.on_event("shutdown")
def shutdown_event():
    """
    서버가 내려갈 때 저장소 정리 함수를 호출한다.

    왜 필요한가? 진짜 MiniRedis는 백그라운드 정리 스레드를 가질 수 있어서,
    프로그램이 끝날 때 깔끔하게 멈추게 해야 하기 때문이다.
    """
    # 저장소가 가진 정리 루틴을 호출한다.
    store.shutdown()
