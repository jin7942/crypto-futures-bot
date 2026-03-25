"""
LLM Sentiment Filter on NostalgiaForInfinityX7.

NostalgiaForInfinityX7 전략을 그대로 사용하면서, OpenClaw LLM 센티먼트 거부권만 추가.
sentiment.json 파일이 없거나 stale이면 neutral fallback → NFI 원본 그대로 동작.

센티먼트 거부권:
    - bearish → 롱 진입 차단
    - bullish → 숏 진입 차단
    - neutral / 파일 없음 → 차단 없음

센티먼트 데이터 흐름:
    [OpenClaw] ── 1~4시간마다 ──> sentiment.json 파일 저장
    [Freqtrade] ── confirm_trade_entry() ──> sentiment.json 읽기 → 거부권 적용
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7

logger = logging.getLogger(__name__)

SENTIMENT_FILE = Path("/freqtrade/user_data/sentiment.json")


class LLMSentimentNFI(NostalgiaForInfinityX7):
    """
    NostalgiaForInfinityX7 + OpenClaw LLM 센티먼트 거부권 필터.

    NFI 원본 로직은 수정하지 않는다. confirm_trade_entry()에서
    센티먼트 기반 거부권만 추가로 적용한다.
    """

    # 센티먼트 캐시 설정
    _sentiment_cache: dict = {}
    _sentiment_cache_ts: float = 0
    _sentiment_cache_ttl: int = 60  # 60초마다 파일 재읽기
    _sentiment_max_age: int = 4 * 3600  # 4시간 초과 시 neutral

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs,
    ) -> bool:
        """
        NFI 진입 확인 + LLM 센티먼트 거부권.

        Args:
            pair: 거래 페어 (e.g., "BTC/USDT:USDT")
            side: "long" 또는 "short"

        Returns:
            True: 진입 허용, False: 진입 거부
        """
        # NFI 원본 로직 먼저 실행
        if not super().confirm_trade_entry(
            pair, order_type, amount, rate, time_in_force,
            current_time, entry_tag, side, **kwargs
        ):
            return False

        # LLM 센티먼트 거부권
        sentiment = self._read_sentiment(pair)

        if side == "long" and sentiment == "bearish":
            logger.info(f"[LLM Veto] {pair} 롱 진입 거부: sentiment={sentiment}")
            return False

        if side == "short" and sentiment == "bullish":
            logger.info(f"[LLM Veto] {pair} 숏 진입 거부: sentiment={sentiment}")
            return False

        return True

    def _read_sentiment(self, pair: str) -> str:
        """
        sentiment.json에서 페어별 센티먼트를 읽는다.

        파일 I/O를 최소화하기 위해 60초 간격으로 캐시.
        파일 없음/파싱 에러/4시간 초과 데이터는 모두 'neutral' 반환.

        Args:
            pair: 거래 페어

        Returns:
            "bullish", "bearish", "neutral" 중 하나
        """
        now = time.time()

        if now - self._sentiment_cache_ts < self._sentiment_cache_ttl:
            return self._get_pair_sentiment(pair)

        try:
            if not SENTIMENT_FILE.exists():
                self._sentiment_cache = {}
                self._sentiment_cache_ts = now
                return "neutral"

            with open(SENTIMENT_FILE, "r") as f:
                self._sentiment_cache = json.load(f)

            self._sentiment_cache_ts = now

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read sentiment file: {e}")
            self._sentiment_cache = {}
            self._sentiment_cache_ts = now

        return self._get_pair_sentiment(pair)

    def _get_pair_sentiment(self, pair: str) -> str:
        """
        캐시에서 특정 페어의 센티먼트를 반환.

        Args:
            pair: 거래 페어

        Returns:
            "bullish", "bearish", "neutral" 중 하나
        """
        if pair not in self._sentiment_cache:
            return "neutral"

        entry = self._sentiment_cache[pair]
        sentiment = entry.get("sentiment", "neutral")

        if sentiment not in ("bullish", "bearish", "neutral"):
            return "neutral"

        updated_at = entry.get("updated_at")
        if updated_at:
            try:
                update_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age_seconds = (datetime.now(timezone.utc) - update_time).total_seconds()
                if age_seconds > self._sentiment_max_age:
                    logger.info(f"Stale sentiment for {pair}: {age_seconds:.0f}s old")
                    return "neutral"
            except (ValueError, TypeError):
                pass

        return sentiment
