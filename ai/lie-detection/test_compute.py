"""CPU↔GPU 스위치 (2026-10-14, infra/compute.sh) — 기본값이 CPU 인지, 셀프 테스트 문이 닫혀 있는지.

GPU 가 없는 CI 에서 도는 시험이다. GPU 실측은 infra/gpu/README.md 의 기록을 본다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app as srv
import deception_vit
import deception_whisper
import feature_extractor as fe
import interview_ws as iw
import selftest

TOKEN = "test-service-token"


def _client():
    # with 없이 — 시작 이벤트(전사 예열)를 돌리지 않는다
    return TestClient(srv.app)


def test_참거짓_모델_장치_기본값은_cpu():
    # auto 가 없다. 아무것도 안 넣으면 cpu — 운영(t3.large) 이 그대로 도는 조건
    assert deception_vit.DEVICE == "cpu"
    assert deception_whisper.DEVICE == "cpu"
    assert fe.VIT_DEVICE == "cpu"
    assert iw.STT_DEVICE == "cpu"


def test_health_가_장치를_낸다():
    compute = _client().get("/health").json()["compute"]
    assert {"stt", "stt_compute_type", "stt_backend", "vit", "deception", "cuda_devices"} <= set(compute)
    assert compute["deception"] == "cpu"


def test_selftest_토큰이_없는_서버는_닫는다(monkeypatch):
    monkeypatch.setattr(srv, "SERVICE_TOKEN", "")
    assert _client().post("/selftest", headers={"X-Service-Token": ""}).status_code == 503


def test_selftest_토큰이_틀리면_401(monkeypatch):
    monkeypatch.setattr(srv, "SERVICE_TOKEN", TOKEN)
    assert _client().post("/selftest").status_code == 401
    assert _client().post("/selftest", headers={"X-Service-Token": "nope"}).status_code == 401


def test_selftest_꺼진_모델은_off_못올린_모델은_unavailable(monkeypatch):
    monkeypatch.setattr(srv, "SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(iw, "STT_MODEL", "")
    monkeypatch.setattr(fe, "VIT_MODEL", "")
    # 모델 내려받기를 시험에서 하지 않는다
    monkeypatch.setattr(deception_vit, "available", lambda: False)
    monkeypatch.setattr(deception_whisper, "available", lambda: False)

    r = _client().post("/selftest", headers={"X-Service-Token": TOKEN})

    assert r.status_code == 200
    models = r.json()["models"]
    assert models["stt"]["status"] == "off"
    assert models["vit"]["status"] == "off"
    assert models["deception_vit"]["status"] == "unavailable"
    assert models["deception_whisper"]["status"] == "unavailable"


def test_selftest_하나가_터져도_나머지는_돈다(monkeypatch):
    monkeypatch.setattr(srv, "SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(fe, "VIT_MODEL", "")
    monkeypatch.setattr(deception_vit, "available", lambda: False)
    monkeypatch.setattr(deception_whisper, "available", lambda: False)

    def boom():
        raise RuntimeError("libcublas.so.12 not found")

    monkeypatch.setattr(selftest, "_stt", boom)

    models = _client().post("/selftest", headers={"X-Service-Token": TOKEN}).json()["models"]

    assert models["stt"]["status"] == "error"
    assert "libcublas" in models["stt"]["detail"]
    assert models["vit"]["status"] == "off"
