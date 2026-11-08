"""FastAPI app: serves run data to the review UI, records editor decisions, and runs new jobs.

Access: if DEMO_ACCESS_CODE is set, every run endpoint needs header
X-Access-Code (the UI asks once and keeps it in memory only). A run started
with the user's own API key is also readable with the X-Run-Token returned at
creation. Keys sent with a request are passed to the provider for that job
only; they are never written to disk or logged.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from coldopen.config import load_config, load_prices
from coldopen.export import edl
from coldopen.models import Atom, Promo, Segment, ShowBible
from coldopen.parse import ParseError
from coldopen.render import descriptor, perceived_atom
from coldopen.timecode import fmt_tc

ROOT = Path(os.environ.get("COLDOPEN_HOME", Path.cwd()))
RUNS = Path(os.environ.get("COLDOPEN_RUNS", ROOT / "runs"))
WEB = Path(os.environ.get("COLDOPEN_WEB", ROOT / "web" / "dist"))
CONFIG = Path(os.environ.get("COLDOPEN_CONFIG", ROOT / "config.yaml"))

app = FastAPI(title="Cold Open", docs_url="/api/docs", openapi_url="/api/openapi.json")
JOBS: dict[str, dict] = {}


# --------------------------------------------------------------------------- access


def _code() -> str | None:
    return os.environ.get("DEMO_ACCESS_CODE") or None


def _check(run_id: str, code: str | None, token: str | None) -> Path:
    if "/" in run_id or ".." in run_id:
        raise HTTPException(400, "Bad run id")
    d = RUNS / run_id
    if not (d / "run_report.json").exists():
        raise HTTPException(404, f"No finished run named {run_id}")
    expected = _code()
    owner = d / ".owner_token"
    if expected and not (code and secrets.compare_digest(code, expected)):
        if not (token and owner.exists() and secrets.compare_digest(token, owner.read_text().strip())):
            raise HTTPException(401, "Access code required")
    return d


def _j(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "access_code_required": bool(_code())}


@app.post("/api/access")
def access(x_access_code: str | None = Header(None)) -> dict:
    expected = _code()
    ok = not expected or bool(x_access_code and secrets.compare_digest(x_access_code, expected))
    if not ok:
        raise HTTPException(401, "That code did not match")
    return {"ok": True}


# --------------------------------------------------------------------------- runs


@app.get("/api/runs")
def list_runs(x_access_code: str | None = Header(None), x_run_token: str | None = Header(None)) -> list[dict]:
    out = []
    if not RUNS.exists():
        return out
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        rep = _j(d / "run_report.json")
        if not rep or not (d / "08_slate.json").exists():
            continue
        try:
            _check(d.name, x_access_code, x_run_token)
        except HTTPException:
            continue
        out.append({
            "id": d.name, "show": rep["show_title"], "date": rep["finished_at"], "models": rep["models"],
            "cost_usd": rep["cost_usd"], "valid": rep["counts"].get("valid", 0), "llm_calls": rep["llm_calls"],
            "seconds": round(sum(rep["stage_seconds"].values()), 1),
        })
    return out


@app.get("/api/runs/{run_id}/show")
def run_show(run_id: str, x_access_code: str | None = Header(None), x_run_token: str | None = Header(None)) -> dict:
    d = _check(run_id, x_access_code, x_run_token)
    meta = _j(d / "00_show.json", {})
    bible = _j(d / "01_bible.json", {})
    detector = _j(d / "01_bible_detector.json", {})
    ekgs = _j(d / "03_ekg.json", [])
    lines = _dialogue_by_second(d)
    return {
        "title": meta.get("title"), "stats": meta.get("stats"), "report": _j(d / "run_report.json"),
        "episodes": [{k: e[k] for k in ("number", "logline", "duration", "scenes")} for e in meta.get("episodes", [])],
        "bible": bible, "labels": detector.get("labels", []), "ekg": ekgs, "lines": lines,
    }


def _atoms(d: Path) -> dict[str, Atom]:
    out = {}
    for line in (d / "00_atoms.jsonl").read_text().splitlines():
        a = Atom(**json.loads(line))
        out[a.id] = a
    return out


def _dialogue_by_second(d: Path) -> dict[str, list]:
    """Per episode, compact [start, end, speaker, text] dialogue rows for the map's hover."""
    out: dict[str, list] = {}
    for a in _atoms(d).values():
        if a.kind == "dialogue":
            out.setdefault(str(a.episode), []).append([a.start, a.end, a.speaker or a.speaker_label, a.text])
    return out


def _cue(a: Atom | None, bible: ShowBible | None) -> dict | None:
    if a is None:
        return None
    return {"label": a.speaker_label, "tags": a.tech_tags + a.emotion_tags, "kind": a.kind,
            "descriptor": descriptor(bible, a) if a.kind == "dialogue" else None}


def _summary(p: dict, slate: dict, atoms: dict[str, Atom] | None = None, bible: ShowBible | None = None) -> dict:
    slot = "hero" if p["id"] == slate["hero"] else "challenger" if p["id"] in slate["challengers"] else \
        "bench" if p["id"] in slate["bench"] else "pool"
    return {
        "id": p["id"], "slot": slot, "structure": p["structure"], "engine": p["engine"],
        "segments": [{k: s[k] for k in ("episode", "start", "end", "start_tc", "end_tc")} for s in p["segments"]],
        "duration": p["duration"], "hook_text": p["hook_text"], "cliffhanger_text": p["cliffhanger_text"],
        "hook_speaker": p["hook_speaker"], "hook_at": p["hook_at"], "why": p["why"], "policy": p["policy"],
        "landing_episode": p["landing_episode"], "free_runway": p["free_runway"], "scores": p["scores"],
        "rationale": slate["rationale"].get(p["id"], ""), "reveals_disclosed": p["reveals_disclosed"],
        "ungrounded_refs": p["ungrounded_refs"], "continuity_warnings": p["continuity_warnings"],
        "hook_cue": _cue(atoms.get(p["validation"].get("hook_id", "")), bible) if atoms else None,
        "cliff_cue": _cue(atoms.get(p["validation"].get("cliffhanger_id", "")), bible) if atoms else None,
    }


@app.get("/api/runs/{run_id}/slate")
def run_slate(run_id: str, x_access_code: str | None = Header(None), x_run_token: str | None = Header(None)) -> dict:
    d = _check(run_id, x_access_code, x_run_token)
    slate = _j(d / "08_slate.json")
    promos = _j(d / "08_promos.json", {})
    order = [slate["hero"], *slate["challengers"], *slate["bench"]]
    rest = sorted((k for k in promos if k not in order), key=lambda k: -promos[k]["scores"]["total"])
    atoms = _atoms(d)
    bible = ShowBible.model_validate_json((d / "01_bible.json").read_text())
    return {
        "slate": slate,
        "promos": [_summary(promos[k], slate, atoms, bible) for k in order + rest],
        "decisions": _decisions(d),
    }


@app.get("/api/runs/{run_id}/promos/{pid}")
def run_promo(run_id: str, pid: str, x_access_code: str | None = Header(None), x_run_token: str | None = Header(None)) -> dict:
    d = _check(run_id, x_access_code, x_run_token)
    promos = _j(d / "08_promos.json", {})
    if pid not in promos:
        raise HTTPException(404, f"No promo {pid}")
    p = promos[pid]
    slate = _j(d / "08_slate.json")
    atoms = _atoms(d)
    bible = ShowBible.model_validate_json((d / "01_bible.json").read_text())
    ekgs = {e["episode"]: e for e in _j(d / "03_ekg.json", [])}
    eps = {e["number"]: e for e in _j(d / "00_show.json", {}).get("episodes", [])}
    context = []
    for s in p["segments"]:
        lo, hi = s["start"] - 20, s["end"] + 20  # room for trim handles
        ep_atoms = sorted((a for a in atoms.values() if a.episode == s["episode"]), key=lambda a: (a.start, a.id))
        context.append({
            "episode": s["episode"], "duration": eps.get(s["episode"], {}).get("duration"),
            "atoms": [_atom_view(a, bible) for a in ep_atoms if a.end > lo and a.start < hi],
            "ekg": ekgs.get(s["episode"], {}).get("values", []),
        })
    return {"promo": p, "summary": _summary(p, slate, atoms, bible), "context": context, "decision": _decisions(d).get(pid)}


def _atom_view(a: Atom, bible: ShowBible) -> dict:
    return {
        "id": a.id, "kind": a.kind, "start": a.start, "end": a.end, "text": a.text, "speaker": a.speaker,
        "label": a.speaker_label, "tags": a.tech_tags + a.emotion_tags, "tc": fmt_tc(a.start),
        "descriptor": descriptor(bible, a) if a.kind == "dialogue" else None,
        "perceived": perceived_atom(a, bible),
    }


@app.get("/api/runs/{run_id}/quality")
def run_quality(run_id: str, x_access_code: str | None = Header(None), x_run_token: str | None = Header(None)) -> dict:
    from coldopen.eval.metrics import comprehension, failure_gallery, rejection_rates

    d = _check(run_id, x_access_code, x_run_token)
    vlog = [json.loads(x) for x in (d / "05_validation_log.jsonl").read_text().splitlines() if x.strip()]
    ev = _j(d / "eval" / "eval_report.json")
    return {
        "report": _j(d / "run_report.json"),
        "eval": ev,
        "validation": rejection_rates(vlog),
        "gallery": ev["failure_gallery"] if ev else failure_gallery(d),
        "comprehension": comprehension(_j(d / "08_promos.json", {})),
    }


# --------------------------------------------------------------------------- decisions + exports


class Decision(BaseModel):
    action: str
    reason: str | None = None
    trims: list[dict] | None = None  # [{"episode", "start", "end"}] per segment


def _decisions(d: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    f = d / "decisions.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["promo_id"]] = r
    return out


@app.post("/api/runs/{run_id}/promos/{pid}/decision")
def decide(run_id: str, pid: str, body: Decision, x_access_code: str | None = Header(None),
           x_run_token: str | None = Header(None)) -> dict:
    d = _check(run_id, x_access_code, x_run_token)
    if body.action not in {"approve_paid", "organic_only", "reject"}:
        raise HTTPException(422, "action must be approve_paid, organic_only or reject")
    if pid not in _j(d / "08_promos.json", {}):
        raise HTTPException(404, f"No promo {pid}")
    rec = {"promo_id": pid, "action": body.action, "reason": body.reason, "trims": body.trims,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with (d / "decisions.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _with_trims(p: dict, dec: dict | None) -> Promo:
    promo = Promo(**p)
    if dec and dec.get("trims") and len(dec["trims"]) == len(promo.segments):
        promo.segments = [
            Segment(episode=s.episode, start=float(t["start"]), end=float(t["end"]), start_tc=fmt_tc(float(t["start"])),
                    end_tc=fmt_tc(float(t["end"])), atom_ids=s.atom_ids)
            for s, t in zip(promo.segments, dec["trims"])
        ]
    return promo


@app.get("/api/runs/{run_id}/export/{name}")
def export(run_id: str, name: str, x_access_code: str | None = Header(None), x_run_token: str | None = Header(None),
           code: str | None = None, token: str | None = None) -> Response:
    # Query-string fallback so a plain <a download> link works; the value is only compared, never stored.
    d = _check(run_id, x_access_code or code, x_run_token or token)
    if name == "promos.csv":
        return FileResponse(d / "promos.csv", media_type="text/csv", filename=f"{run_id}-promos.csv")
    if name.endswith(".edl"):
        pid = name[:-4]
        promos = _j(d / "08_promos.json", {})
        if pid not in promos:
            raise HTTPException(404, f"No promo {pid}")
        cfg = load_config(CONFIG) if CONFIG.exists() else None
        text = edl(_with_trims(promos[pid], _decisions(d).get(pid)), cfg.fps if cfg else 30)
        return PlainTextResponse(text, headers={"Content-Disposition": f'attachment; filename="{pid}.edl"'})
    raise HTTPException(404, "Unknown export")


# --------------------------------------------------------------------------- models + new runs


@app.get("/api/models")
def models() -> dict:
    cfg = load_config(CONFIG)
    known = sorted(set(load_prices().keys()) | set(cfg.models.values()))
    return {"roles": cfg.models, "options": known}


@app.post("/api/runs")
async def create_run(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    provider: str = Form("live"),
    miner: str | None = Form(None),
    judge: str | None = Form(None),
    classifier: str | None = Form(None),
    api_key: str | None = Form(None),
    max_episodes: int | None = Form(None),
    x_access_code: str | None = Header(None),
) -> dict:
    from coldopen.llm.provider import LLMClient, LiveProvider

    expected = _code()
    has_code = bool(expected and x_access_code and secrets.compare_digest(x_access_code, expected)) or not expected
    if not has_code and not api_key and provider != "mock":
        raise HTTPException(401, "Enter the access code or your own API key")
    if provider not in {"live", "mock"}:
        raise HTTPException(422, "provider must be live or mock")
    cfg = load_config(CONFIG)
    for role, val in (("miner", miner), ("judge", judge), ("classifier", classifier)):
        if val:
            cfg.models[role] = val
    if provider == "live" and any("TODO" in m for m in cfg.models.values()):
        raise HTTPException(422, "Choose a real model for every role")

    data = await file.read()
    work = Path(tempfile.mkdtemp(prefix="coldopen-"))
    src = work / "input.zip"
    src.write_bytes(data)
    if not zipfile.is_zipfile(io.BytesIO(data)):
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(422, "Upload a .zip of episode .txt files")

    job = uuid.uuid4().hex[:12]
    run_id = f"upload-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{job[:4]}"
    token = secrets.token_urlsafe(16)
    JOBS[job] = {"run_id": run_id, "events": [], "done": False}
    events: list[dict] = JOBS[job]["events"]  # append-only; every subscriber reads it by index
    if api_key:
        keys = {p: api_key for p in {m.split("/", 1)[0] for m in cfg.models.values()}}
        prov: Any = LiveProvider(api_keys=keys)
    else:
        prov = provider

    async def go():
        from coldopen.pipeline import Pipeline

        out = RUNS / run_id
        try:
            client = LLMClient(cfg, provider=prov, prices=load_prices(), run_dir=out)

            def emit(e: dict) -> None:
                events.append(e)

            out.mkdir(parents=True, exist_ok=True)
            (out / ".owner_token").write_text(token)
            await Pipeline(src, out, cfg, client, title=title or None, max_episodes=max_episodes, emit=emit).run()
        except ParseError as e:
            events.append({"type": "error", "message": f"Parse error: {e}"})
        except asyncio.CancelledError:
            events.append({"type": "error", "message": "The run was cancelled (server shutting down?)"})
            raise
        except Exception as e:  # noqa: BLE001 - report to the UI; never echo keys
            events.append({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"})
        finally:
            JOBS[job]["done"] = True
            events.append({"type": "end", "run_id": run_id})
            shutil.rmtree(work, ignore_errors=True)

    # Keep a reference: an unreferenced task can be garbage-collected mid-run.
    JOBS[job]["task"] = asyncio.create_task(go())
    return {"job_id": job, "run_id": run_id, "run_token": token}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    job = JOBS[job_id]

    async def stream():
        i = 0
        while True:
            if await request.is_disconnected():
                return
            while i < len(job["events"]):
                e = job["events"][i]
                i += 1
                yield {"data": json.dumps(e)}
                if e.get("type") == "end":
                    return
            await asyncio.sleep(0.1)

    return EventSourceResponse(stream())


# --------------------------------------------------------------------------- frontend


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = WEB / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB / "index.html")
