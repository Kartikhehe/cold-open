"""API: access control, run data, decisions, exports, and a mock upload job."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from coldopen.config import Config
from coldopen.llm.mockbrain import MockBrain
from coldopen.llm.provider import LLMClient
from coldopen.pipeline import Pipeline
from tests.helpers import FIX

CFG = Config(models={"miner": "m/a", "judge": "m/b", "classifier": "m/c"}, rpm=100000, concurrency=8)


@pytest.fixture
def api(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    out = runs / "mini"
    asyncio.run(Pipeline(FIX / "mini_show", out, CFG, LLMClient(CFG, provider=MockBrain(), prices={}, run_dir=out)).run())
    import coldopen.api.server as server

    monkeypatch.setattr(server, "RUNS", runs)
    monkeypatch.setenv("DEMO_ACCESS_CODE", "letmein")
    # One client session = one event loop, like uvicorn; background jobs survive between requests.
    with TestClient(server.app) as client:
        yield client, {"X-Access-Code": "letmein"}


def test_access_code_required(api):
    c, h = api
    assert c.get("/api/runs/mini/slate").status_code == 401
    assert c.get("/api/runs").json() == []
    assert c.post("/api/access", headers={"X-Access-Code": "nope"}).status_code == 401
    assert [r["id"] for r in c.get("/api/runs", headers=h).json()] == ["mini"]


def test_show_slate_promo(api):
    c, h = api
    show = c.get("/api/runs/mini/show", headers=h).json()
    assert len(show["ekg"]) == 3 and show["bible"]["characters"]
    sl = c.get("/api/runs/mini/slate", headers=h).json()
    hero = sl["slate"]["hero"]
    assert sl["promos"][0]["id"] == hero and sl["promos"][0]["slot"] == "hero"
    pr = c.get(f"/api/runs/mini/promos/{hero}", headers=h).json()
    assert pr["context"][0]["atoms"] and "perceived" in pr["context"][0]["atoms"][0]


def test_decision_persists_and_trims_edl(api):
    c, h = api
    hero = c.get("/api/runs/mini/slate", headers=h).json()["slate"]["hero"]
    seg = c.get(f"/api/runs/mini/promos/{hero}", headers=h).json()["promo"]["segments"]
    trims = [{"episode": s["episode"], "start": s["start"] + 1.0, "end": s["end"]} for s in seg]
    r = c.post(f"/api/runs/mini/promos/{hero}/decision", headers=h, json={"action": "approve_paid", "trims": trims})
    assert r.status_code == 200
    assert c.get("/api/runs/mini/slate", headers=h).json()["decisions"][hero]["action"] == "approve_paid"
    edl = c.get(f"/api/runs/mini/export/{hero}.edl", headers=h).text
    assert edl.startswith(f"TITLE: {hero}") and "FCM: NON-DROP FRAME" in edl
    assert c.post(f"/api/runs/mini/promos/{hero}/decision", headers=h, json={"action": "bogus"}).status_code == 422
    assert c.get("/api/runs/mini/export/promos.csv", params={"code": "letmein"}).status_code == 200


def test_upload_runs_a_mock_job(api):
    c, h = api
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in (FIX / "mini_show").glob("*.txt"):
            z.write(f, f"Mini/{f.name}")
    r = c.post("/api/runs", files={"file": ("show.zip", buf.getvalue(), "application/zip")},
               data={"provider": "mock"}, headers=h)
    assert r.status_code == 200, r.text
    job = r.json()
    with c.stream("GET", f"/api/jobs/{job['job_id']}/events") as s:
        events = [json.loads(line[5:]) for line in s.iter_lines() if line.startswith("data:")]
    assert events[-1]["type"] == "end" and any(e.get("stage") == "slate" for e in events)
    assert c.get(f"/api/runs/{job['run_id']}/slate", headers={"X-Run-Token": job["run_token"]}).status_code == 200
