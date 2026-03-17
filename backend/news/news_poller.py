from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List

import httpx
import redis.asyncio as redis

from backend.config import AppConfig
from backend.news.sentiment_scorer import SentimentResult, SentimentScorer


@dataclass
class NewsEvent:
    ticker: str
    headline: str
    text: str
    timestamp: datetime
    sentiment: SentimentResult

    def to_payload(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "headline": self.headline,
            "text": self.text,
            "timestamp": self.timestamp.isoformat(),
            "compound": self.sentiment.compound,
            "label": self.sentiment.label,
        }


class NewsPoller:
    """Polls NewsAPI and pushes strong-sentiment events into Redis."""

    def __init__(self, cfg: AppConfig, redis_client: redis.Redis):
        self.cfg = cfg
        self.redis = redis_client
        self.api_key = os.getenv("NEWSAPI_KEY")
        self._task: asyncio.Task | None = None
        self._seen_key = "news:seen_urls"
        self._queue_key = "news:events"
        thresh = 0.70
        scfg = cfg.strategies.get("sentiment_catalyst")
        if scfg and scfg.sentiment_threshold is not None:
            thresh = scfg.sentiment_threshold
        self._scorer = SentimentScorer(threshold=thresh)

    async def start(self) -> None:
        if not self.api_key:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                await self._poll_once()
            except Exception:
                # best-effort; errors can be logged in future
                pass
            await asyncio.sleep(60)

    async def _poll_once(self) -> None:
        if not self.cfg.watchlist:
            return
        symbols = " OR ".join(self.cfg.watchlist[:20])
        params = {
            "q": symbols,
            "language": "en",
            "pageSize": 50,
            "sortBy": "publishedAt",
        }
        headers = {"X-Api-Key": self.api_key}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything", params=params, headers=headers
            )
        if resp.status_code != 200:
            return
        data = resp.json()
        articles: List[dict[str, Any]] = data.get("articles", [])
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=30)

        pipe = self.redis.pipeline()
        for art in articles:
            url = art.get("url") or ""
            if not url:
                continue
            if await self.redis.sismember(self._seen_key, url):
                continue
            published_str = art.get("publishedAt") or ""
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if published < cutoff:
                continue
            title = art.get("title") or ""
            desc = art.get("description") or ""
            content = art.get("content") or ""
            text = f"{title}. {desc} {content}".strip()
            sentiment = self._scorer.score(text)
            if sentiment.label == "IGNORE":
                continue
            # crude ticker detection: look for any watchlist symbol in title
            tickers = [t for t in self.cfg.watchlist if t in title]
            if not tickers:
                continue
            payload = None
            for ticker in tickers:
                ev = NewsEvent(
                    ticker=ticker,
                    headline=title,
                    text=text,
                    timestamp=published,
                    sentiment=sentiment,
                )
                payload = ev.to_payload()
                await self.redis.rpush(self._queue_key, httpx.dumps(payload))
            pipe.sadd(self._seen_key, url)
        await pipe.execute()

