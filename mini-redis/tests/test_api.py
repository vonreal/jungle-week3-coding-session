import os
import time

import pytest
from fastapi.testclient import TestClient

from mini_redis.api import app, store


class TestAPI:
    """C 담당: API E2E 테스트"""

    def setup_method(self):
        """
        각 테스트 전에 저장소를 비운다.

        왜 필요한가? 앞 테스트에서 남긴 값이 뒤 테스트를 헷갈리게 만들면
        실패 원인을 읽기 어려워지기 때문이다.
        """
        # 테스트는 항상 빈 저장소에서 시작하는 편이 읽기 쉽다.
        store.flush()

    def test_set_and_get(self):
        """
        POST /set 후 GET /get/{key}가 같은 값을 돌려주는지 본다.

        비유: 사물함에 물건을 넣고 다시 열어 봤을 때
        같은 물건이 나오는지 확인하는 가장 기본 검사다.
        """
        client = TestClient(app)

        # 먼저 값을 저장한다.
        res = client.post("/set", json={"key": "name", "value": "alice"})
        assert res.status_code == 200
        assert res.json()["status"] == "OK"

        # 같은 키를 다시 읽으면 저장한 값이 보여야 한다.
        res = client.get("/get/name")
        assert res.status_code == 200
        assert res.json()["value"] == "alice"

    def test_get_nonexistent(self):
        """
        없는 키를 읽으면 404가 나오는지 본다.

        왜 필요한가? "없음"과 "서버 에러"는 완전히 다른 상황이라서
        API가 분명하게 구분해 줘야 하기 때문이다.
        """
        client = TestClient(app)
        res = client.get("/get/ghost")
        assert res.status_code == 404
        assert res.json()["detail"] == "Key not found"

    def test_set_empty_key(self):
        """
        빈 키를 저장하려고 하면 400 에러가 나는지 본다.

        비유: 이름표 없는 상자는 나중에 찾을 수 없으니
        처음부터 받지 않는 규칙을 검사하는 테스트다.
        """
        client = TestClient(app)
        res = client.post("/set", json={"key": "", "value": "data"})
        assert res.status_code == 400
        assert res.json()["detail"] == "Key cannot be empty"

    def test_delete(self):
        """
        DELETE /del/{key}가 실제로 값을 지우는지 본다.

        왜 필요한가? 삭제 성공 응답만 보고 믿지 말고,
        진짜로 다시 조회했을 때 없어져야 제대로 지운 것이다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "name", "value": "alice"})

        # 삭제 응답에는 deleted=True가 들어 있어야 한다.
        res = client.delete("/del/name")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        # 지운 뒤 다시 읽으면 404가 나와야 한다.
        res = client.get("/get/name")
        assert res.status_code == 404

    def test_delete_nonexistent(self):
        """
        없는 키를 지울 때 deleted=False가 오는지 본다.

        왜 필요한가? 삭제 API는 "성공적으로 요청을 처리했다"와
        "실제로 지운 데이터가 있었다"를 구분해서 말해줘야 하기 때문이다.
        """
        client = TestClient(app)
        res = client.delete("/del/ghost")
        assert res.status_code == 200
        assert res.json()["deleted"] is False

    def test_keys(self):
        """
        GET /keys가 저장된 키 목록을 돌려주는지 본다.

        왜 필요한가? 대시보드 목록 패널이 이 API를 기준으로 화면을 그리기 때문이다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "a", "value": "1"})
        client.post("/set", json={"key": "b", "value": "2", "ttl": 60})

        # 키 이름만 뽑아 두면 포함 여부를 읽기 쉽다.
        res = client.get("/keys")
        assert res.status_code == 200
        keys_data = res.json()
        key_names = [item["key"] for item in keys_data]

        assert "a" in key_names
        assert "b" in key_names

    def test_set_with_ttl(self):
        """
        TTL을 준 키가 /keys에서 남은 시간을 보여주는지 본다.

        왜 필요한가? 대시보드가 TTL 숫자를 보여주려면
        이 API가 None이 아닌 양수를 내줘야 하기 때문이다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "temp", "value": "data", "ttl": 60})

        # temp 키의 ttl 필드가 양수인지 확인한다.
        res = client.get("/keys")
        temp_info = [item for item in res.json() if item["key"] == "temp"][0]

        assert temp_info["ttl"] is not None
        assert temp_info["ttl"] > 0

    def test_info(self):
        """
        GET /info가 저장소 요약 정보를 잘 주는지 본다.

        왜 필요한가? 대시보드 상단 숫자 카드가
        total_keys 같은 값을 정확히 보여줘야 하기 때문이다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "a", "value": "1"})
        client.post("/set", json={"key": "b", "value": "2", "ttl": 60})

        # 총 키 수와 TTL 키 수를 함께 확인한다.
        res = client.get("/info")
        assert res.status_code == 200
        info = res.json()

        assert info["total_keys"] == 2
        assert info["keys_with_ttl"] == 1
        assert info["keys_without_ttl"] == 1

    def test_flush(self):
        """
        POST /flush가 전체 데이터를 비우는지 본다.

        비유: 칠판 지우개로 한 번에 모두 지운 뒤
        정말 빈 칠판이 됐는지 확인하는 검사다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "a", "value": "1"})

        # 전체 삭제 뒤에는 키 목록이 비어 있어야 한다.
        res = client.post("/flush")
        assert res.status_code == 200
        assert res.json()["status"] == "OK"

        res = client.get("/keys")
        assert res.status_code == 200
        assert len(res.json()) == 0

    def test_run_tests(self):
        """
        POST /run-tests가 결과 구조를 돌려주는지 본다.

        주의: 이 테스트가 /run-tests 안에서 다시 실행되면
        pytest가 자기 자신을 계속 부를 수 있으니,
        중첩 실행에서는 건너뛴다.
        """
        if os.getenv("MINI_REDIS_SKIP_NESTED_RUN_TESTS") == "1":
            pytest.skip("Skip nested /run-tests invocation")

        client = TestClient(app)

        # 상세 결과 내용은 환경마다 달라도, 필드 구조는 유지돼야 한다.
        res = client.post("/run-tests")
        assert res.status_code == 200
        data = res.json()

        assert "passed" in data
        assert "output" in data
        assert "errors" in data

    def test_dashboard(self):
        """
        GET /dashboard가 HTML 문서를 돌려주는지 본다.

        왜 필요한가? 브라우저에서 대시보드 페이지를 여는 진입점이기 때문이다.
        """
        client = TestClient(app)
        res = client.get("/dashboard")

        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        assert "Mini Redis Dashboard" in res.text

    def test_run_benchmark(self):
        """
        POST /run-benchmark가 성능 비교 숫자를 돌려주는지 본다.

        왜 필요한가? 대시보드의 차트 패널이 이 응답 구조를 그대로 사용하기 때문이다.
        """
        client = TestClient(app)
        res = client.post("/run-benchmark")

        assert res.status_code == 200
        data = res.json()

        assert "without_cache" in data
        assert "with_cache" in data
        assert "speedup" in data

    def test_ttl_expiry_returns_404(self):
        """
        TTL이 지난 키는 다시 읽을 수 없어야 한다.

        왜 필요한가? 저장은 됐어도 시간이 지나면 사라져야 TTL 기능이 의미가 있기 때문이다.
        """
        client = TestClient(app)
        client.post("/set", json={"key": "soon", "value": "gone", "ttl": 1})

        # 실제 만료를 기다린 뒤 조회하면 404여야 한다.
        time.sleep(1.1)
        res = client.get("/get/soon")

        assert res.status_code == 404
