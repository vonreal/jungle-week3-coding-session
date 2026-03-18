import pytest
from fastapi.testclient import TestClient

from mini_redis.api import app


class TestAPI:
    """C 담당: API E2E 테스트"""

    def test_set_and_get(self):
        """POST /set → GET /get/{key}"""
        pass

    def test_delete(self):
        """DELETE /del/{key}"""
        pass

    def test_keys(self):
        """GET /keys"""
        pass

