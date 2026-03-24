"""
LLM Hybrid Strategy for Crypto Futures Trading.

NostalgiaForInfinity 기반 기술적 지표 + OpenClaw LLM 시장 국면 필터.
LLM은 진입 시그널에 대한 거부권만 보유하며, 시그널 생성 권한은 없다.

센티먼트 데이터는 OpenClaw가 주기적으로 생성하여 sentiment.json에 저장하고,
Freqtrade 전략이 이 파일을 읽어서 필터링에 사용한다.
"""

import json
import logging
import time
from datetime import datetime, timezone
from functools import reduce
from pathlib import Path
from typing import Optional

import numpy as np
import talib.abstract as ta
from freqtrade.strategy import (
    DecimalParameter,
    IntParameter,
    IStrategy,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)

# sentiment.json 기본 경로 (Docker 볼륨 마운트 기준)
SENTIMENT_FILE = Path("/freqtrade/user_data/sentiment.json")


class LLMHybridStrategy(IStrategy):
    """
    하이브리드 전략: 기술적 지표 + OpenClaw LLM 시장 국면 필터.

    - 기술적 지표: RSI, Bollinger Bands, EMA, MACD, Volume
    - LLM 필터: OpenClaw가 생성한 sentiment.json 파일 읽기
    - LLM은 거부권만 보유: bearish 판단 시 롱 진입 차단, bullish 판단 시 숏 진입 차단

    센티먼트 연동 방식:
        [OpenClaw] ── 1~4시간마다 ──> sentiment.json 파일 저장
        [Freqtrade] ── 매 캔들마다 ──> sentiment.json 파일 읽기

    sentiment.json 형식:
        {
            "BTC/USDT:USDT": {
                "sentiment": "bullish",
                "confidence": 0.7,
                "updated_at": "2026-03-24T12:00:00Z"
            }
        }
    """

    # Strategy interface version
    INTERFACE_VERSION = 3

    # Futures settings
    can_short = True
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # ROI table
    minimal_roi = {
        "0": 0.10,
        "30": 0.05,
        "60": 0.03,
        "120": 0.01,
    }

    # Timeframe
    timeframe = "5m"
    process_only_new_candles = True
    startup_candle_count: int = 200

    # Sentiment file settings
    _sentiment_cache: dict = {}
    _sentiment_cache_ts: float = 0
    _sentiment_cache_ttl: int = 60  # 파일을 60초마다 다시 읽기 (I/O 최소화)
    _sentiment_max_age: int = 4 * 3600  # 4시간 이상 지난 센티먼트는 무시

    # Hyperoptable parameters
    buy_rsi = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 80, default=70, space="sell", optimize=True)
    buy_bb_factor = DecimalParameter(0.95, 1.0, default=0.98, space="buy", optimize=True)
    sell_bb_factor = DecimalParameter(1.0, 1.05, default=1.02, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        기술적 지표 계산 + OpenClaw 센티먼트 읽기.

        Args:
            dataframe: OHLCV 데이터프레임
            metadata: 페어 메타데이터 (pair, stake_currency 등)

        Returns:
            지표가 추가된 데이터프레임
        """
        # RSI
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_width"] = (
            (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_middle"]
        )

        # EMA
        dataframe["ema_9"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)

        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # Volume
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(window=20).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean_20"]

        # ATR (Average True Range) for volatility
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # OpenClaw sentiment (file-based)
        pair = metadata["pair"]
        dataframe["llm_sentiment"] = self._read_sentiment(pair)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        진입 시그널 생성. LLM 거부권 적용.

        Long 조건: RSI 과매도 + BB 하단 돌파 + LLM bearish 아닌 경우
        Short 조건: RSI 과매수 + BB 상단 돌파 + LLM bullish 아닌 경우
        """
        # Long entry
        conditions_long = [
            dataframe["rsi"] < self.buy_rsi.value,
            dataframe["close"] < dataframe["bb_lower"] * self.buy_bb_factor.value,
            dataframe["volume_ratio"] > 1.0,
            dataframe["ema_9"] > dataframe["ema_21"],
            dataframe["llm_sentiment"] != "bearish",  # LLM veto
        ]
        dataframe.loc[reduce(np.bitwise_and, conditions_long), "enter_long"] = 1

        # Short entry
        conditions_short = [
            dataframe["rsi"] > self.sell_rsi.value,
            dataframe["close"] > dataframe["bb_upper"] * self.sell_bb_factor.value,
            dataframe["volume_ratio"] > 1.0,
            dataframe["ema_9"] < dataframe["ema_21"],
            dataframe["llm_sentiment"] != "bullish",  # LLM veto
        ]
        dataframe.loc[reduce(np.bitwise_and, conditions_short), "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        청산 시그널 생성.

        Long exit: RSI 과매수 + BB 중앙선 위
        Short exit: RSI 과매도 + BB 중앙선 아래
        """
        # Long exit
        conditions_exit_long = [
            dataframe["rsi"] > self.sell_rsi.value,
            dataframe["close"] > dataframe["bb_middle"],
        ]
        dataframe.loc[reduce(np.bitwise_and, conditions_exit_long), "exit_long"] = 1

        # Short exit
        conditions_exit_short = [
            dataframe["rsi"] < self.buy_rsi.value,
            dataframe["close"] < dataframe["bb_middle"],
        ]
        dataframe.loc[reduce(np.bitwise_and, conditions_exit_short), "exit_short"] = 1

        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        레버리지 설정. 안전 상한선 3x 고정.

        Returns:
            레버리지 배수 (최대 3x)
        """
        return 3.0

    # ──────────────────────────────────────────────
    # Sentiment File Reader (Private Methods)
    # ──────────────────────────────────────────────

    def _read_sentiment(self, pair: str) -> str:
        """
        OpenClaw가 생성한 sentiment.json에서 페어별 센티먼트를 읽는다.

        파일 I/O를 최소화하기 위해 60초 간격으로 캐시.
        파일 없음/파싱 에러/4시간 초과 데이터는 모두 'neutral' 반환.

        Args:
            pair: 거래 페어 (e.g., "BTC/USDT:USDT")

        Returns:
            "bullish", "bearish", "neutral" 중 하나
        """
        now = time.time()

        # 캐시가 유효하면 파일을 다시 읽지 않음
        if now - self._sentiment_cache_ts < self._sentiment_cache_ttl:
            return self._get_pair_sentiment(pair)

        # sentiment.json 파일 읽기
        try:
            if not SENTIMENT_FILE.exists():
                logger.debug(f"Sentiment file not found: {SENTIMENT_FILE}")
                self._sentiment_cache = {}
                self._sentiment_cache_ts = now
                return "neutral"

            with open(SENTIMENT_FILE, "r") as f:
                self._sentiment_cache = json.load(f)

            self._sentiment_cache_ts = now
            logger.debug(f"Sentiment file loaded: {len(self._sentiment_cache)} pairs")

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read sentiment file: {e}")
            self._sentiment_cache = {}
            self._sentiment_cache_ts = now

        return self._get_pair_sentiment(pair)

    def _get_pair_sentiment(self, pair: str) -> str:
        """
        캐시에서 특정 페어의 센티먼트를 반환.

        4시간 이상 지난 데이터는 stale로 판단하여 'neutral' 반환.

        Args:
            pair: 거래 페어

        Returns:
            "bullish", "bearish", "neutral" 중 하나
        """
        if pair not in self._sentiment_cache:
            return "neutral"

        entry = self._sentiment_cache[pair]
        sentiment = entry.get("sentiment", "neutral")

        # 유효한 값인지 검증
        if sentiment not in ("bullish", "bearish", "neutral"):
            return "neutral"

        # updated_at이 있으면 staleness 체크
        updated_at = entry.get("updated_at")
        if updated_at:
            try:
                update_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age_seconds = (datetime.now(timezone.utc) - update_time).total_seconds()
                if age_seconds > self._sentiment_max_age:
                    logger.info(f"Stale sentiment for {pair}: {age_seconds:.0f}s old, using neutral")
                    return "neutral"
            except (ValueError, TypeError):
                pass

        return sentiment
