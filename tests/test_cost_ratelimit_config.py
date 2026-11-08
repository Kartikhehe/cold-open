"""Cost accounting, the rate limiter, and config loading."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from coldopen.config import Config, load_config
from coldopen.llm.cost import UsageTotals, cost_of
from coldopen.llm.ratelimit import RateLimiter

ROOT = Path(__file__).resolve().parent.parent


def test_cost_known_todo_unknown(prices):
    assert cost_of("fake/miner-a", 1_000_000, 500_000, prices).usd == pytest.approx(2.0)
    todo = cost_of("fake/judge-b", 10, 10, prices)
    assert todo.usd is None and todo.list_price_equivalent
    assert cost_of("nobody/knows", 10, 10, prices).usd is None


def test_usage_totals_go_null_once_unknown(prices):
    u = UsageTotals()
    u.add(10, 10, cost_of("fake/miner-a", 10, 10, prices), cached=False)
    assert u.cost_usd is not None
    u.add(10, 10, cost_of("x/y", 10, 10, prices), cached=True)
    assert u.cost_usd is None and u.cache_hits == 1 and u.calls == 2


def test_token_bucket_waits_when_empty():
    now = [0.0]
    slept: list[float] = []

    async def fake_sleep(s):
        slept.append(s)
        now[0] += s

    lim = RateLimiter(concurrency=5, rpm=2, clock=lambda: now[0], sleep=fake_sleep)

    async def go():
        for _ in range(3):
            async with lim:
                pass

    asyncio.run(go())
    assert slept and sum(slept) == pytest.approx(30.0, rel=0.01)  # 3rd call waits 60/rpm s


def test_concurrency_cap():
    lim = RateLimiter(concurrency=2, rpm=1000)
    active, peak = 0, 0

    async def job():
        nonlocal active, peak
        async with lim:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    async def go():
        await asyncio.gather(*(job() for _ in range(6)))

    asyncio.run(go())
    assert peak == 2


def test_repo_config_loads():
    cfg = load_config(ROOT / "config.yaml")
    assert set(cfg.models) >= {"miner", "judge", "classifier"}
    assert sum(cfg.weights.model_dump().values()) == pytest.approx(1.0)


def test_config_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        Config.model_validate({"models": {}, "wieghts": {}})
