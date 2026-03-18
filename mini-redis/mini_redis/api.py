import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mini_redis.store import MiniRedis

app = FastAPI(title="Mini Redis", version="0.1.0")
store = MiniRedis()
benchmark_jobs: dict[str, dict] = {}
benchmark_jobs_lock = threading.Lock()
test_jobs: dict[str, dict] = {}
test_jobs_lock = threading.Lock()


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


class BenchmarkStartResponse(BaseModel):
    """개별 벤치마크 작업 시작 응답 형식."""

    job_id: str
    scenario: str
    status: str


class TestStartResponse(BaseModel):
    """백그라운드 테스트 실행 시작 응답 형식."""

    job_id: str
    status: str


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


@app.post("/run-tests/start", response_model=TestStartResponse)
def start_tests():
    """
    pytest를 백그라운드에서 시작하고 작업 ID를 돌려주는 API.

    왜 필요한가? 대시보드에서 CLI처럼 출력이 조금씩 쌓이는 모습을 보여주려면
    요청 하나가 끝날 때까지 기다리지 말고, 작업을 먼저 시작한 뒤 상태를 따로 읽어야 한다.
    """
    project_root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["MINI_REDIS_SKIP_NESTED_RUN_TESTS"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    job_id = uuid.uuid4().hex
    with test_jobs_lock:
        test_jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "output": "",
            "errors": "",
            "passed": None,
            "returncode": None,
        }

    def worker() -> None:
        process = None
        try:
            # 줄 단위로 읽으려면 stdout/stderr를 pipe로 열고 text 모드를 쓴다.
            process = subprocess.Popen(
                [sys.executable, "-m", "pytest", "--tb=short", "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=project_root,
                env=env,
                bufsize=1,
            )

            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            def read_stream(stream, target_chunks, field_name: str) -> None:
                # pytest가 흘려보내는 줄을 하나씩 모아 대시보드가 바로 읽을 수 있게 한다.
                for line in iter(stream.readline, ""):
                    target_chunks.append(line)
                    with test_jobs_lock:
                        if job_id in test_jobs:
                            test_jobs[job_id][field_name] = "".join(target_chunks)
                stream.close()

            stdout_thread = threading.Thread(
                target=read_stream,
                args=(process.stdout, stdout_chunks, "output"),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=read_stream,
                args=(process.stderr, stderr_chunks, "errors"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            process.wait(timeout=60)
            stdout_thread.join()
            stderr_thread.join()

            with test_jobs_lock:
                test_jobs[job_id].update(
                    {
                        "status": "completed",
                        "passed": process.returncode == 0,
                        "returncode": process.returncode,
                        "output": "".join(stdout_chunks),
                        "errors": "".join(stderr_chunks),
                    }
                )
        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
            with test_jobs_lock:
                test_jobs[job_id].update(
                    {
                        "status": "failed",
                        "passed": False,
                        "returncode": -1,
                        "errors": "Pytest timed out after 60 seconds",
                    }
                )
        except Exception as exc:
            with test_jobs_lock:
                test_jobs[job_id].update(
                    {
                        "status": "failed",
                        "passed": False,
                        "returncode": -1,
                        "errors": str(exc),
                    }
                )

    threading.Thread(target=worker, daemon=True).start()
    return TestStartResponse(job_id=job_id, status="running")


@app.get("/run-tests/status/{job_id}")
def get_test_status(job_id: str):
    """
    백그라운드 테스트 작업의 현재 상태를 조회하는 API.

    왜 필요한가? 대시보드가 "지금 어디까지 출력됐는지"를
    일정 간격으로 읽어와서 화면에 이어 붙일 수 있어야 하기 때문이다.
    """
    with test_jobs_lock:
        job = test_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Test job not found")
        return job


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


@app.post("/run-benchmark/{scenario_name}", response_model=BenchmarkStartResponse)
def run_benchmark_scenario(scenario_name: str):
    """
    벤치마크 시나리오 하나를 백그라운드로 시작하는 API.

    왜 필요한가? 대시보드에서 시나리오별 버튼을 누르고,
    끝날 때까지 진행 상황을 중간중간 보여주려면
    요청을 바로 끝내고 뒤에서 작업을 이어가야 하기 때문이다.
    """
    from benchmark import (
        SCENARIO_1_NAME,
        SCENARIO_2_NAME,
        SCENARIO_3_NAME,
        run_named_scenario,
    )

    allowed_scenarios = {SCENARIO_1_NAME, SCENARIO_2_NAME, SCENARIO_3_NAME}
    if scenario_name not in allowed_scenarios:
        raise HTTPException(status_code=400, detail="Unknown benchmark scenario")

    job_id = uuid.uuid4().hex
    with benchmark_jobs_lock:
        benchmark_jobs[job_id] = {
            "job_id": job_id,
            "scenario": scenario_name,
            "status": "running",
            "phase": "starting",
            "elapsed_ms": 0,
            "current_loaded": 0,
            "total_ops": 0,
            "result": None,
            "error": None,
        }

    def update_progress(progress: dict) -> None:
        # 백그라운드 작업이 보낸 진행 상황을 현재 작업 표에 덮어쓴다.
        with benchmark_jobs_lock:
            if job_id in benchmark_jobs:
                benchmark_jobs[job_id].update(progress)

    def worker() -> None:
        try:
            result = run_named_scenario(scenario_name, progress_callback=update_progress)
            with benchmark_jobs_lock:
                benchmark_jobs[job_id].update(
                    {
                        "status": "completed",
                        "phase": "completed",
                        "result": result,
                    }
                )
        except Exception as exc:
            with benchmark_jobs_lock:
                benchmark_jobs[job_id].update(
                    {
                        "status": "failed",
                        "phase": "failed",
                        "error": str(exc),
                    }
                )

    threading.Thread(target=worker, daemon=True).start()
    return BenchmarkStartResponse(job_id=job_id, scenario=scenario_name, status="running")


@app.get("/benchmark-status/{job_id}")
def get_benchmark_status(job_id: str):
    """
    벤치마크 작업의 현재 상태를 조회하는 API.

    비유: 오븐에 넣어 둔 빵이 "지금 몇 분 지났는지, 거의 끝났는지"를
    밖에서 보는 창문 같은 역할이다.
    """
    with benchmark_jobs_lock:
        job = benchmark_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Benchmark job not found")
        return job


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
