"""
LLM Hybrid Strategy for Crypto Futures Trading.

NostalgiaForInfinity 기반 기술적 지표 + Claude LLM 시장 국면 필터.
LLM은 진입 시그널에 대한 거부권만 보유하며, 시그널 생성 권한은 없다.
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
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
)
from pandas import DataFrame

logger = logging.getLogger(__name__)


class LLMHybridStrategy(IStrategy):
    """
    하이브리드 전략: 기술적 지표 + LLM 시장 국면 필터.

    - 기술적 지표: RSI, Bollinger Bands, EMA, MACD, Volume
    - LLM 필터: Claude API를 통한 시장 센티먼트 판단 (1~4시간 캐시)
    - LLM은 거부권만 보유: bearish 판단 시 롱 진입 차단, bullish 판단 시 숏 진입 차단
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

    # LLM cache settings
    _llm_cache: dict = {}
    _llm_cache_ttl: int = 4 * 3600  # 4 hours in seconds
    _llm_enabled: bool = True

    # Hyperoptable parameters
    buy_rsi = IntParameter(20, 40, default=30, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 80, default=70, space="sell", optimize=True)
    buy_bb_factor = DecimalParameter(0.95, 1.0, default=0.98, space="buy", optimize=True)
    sell_bb_factor = DecimalParameter(1.0, 1.05, default=1.02, space="sell", optimize=True)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        기술적 지표 계산 + LLM 센티먼트 업데이트.

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

        # LLM sentiment (cached, 4-hour intervals)
        pair = metadata["pair"]
        dataframe["llm_sentiment"] = self._get_cached_sentiment(pair, dataframe)

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
        레버리지 설정. config.json의 leverage 설정을 따르되 안전 상한선 적용.

        Returns:
            레버리지 배수 (최대 3x)
        """
        return 3.0

    # ──────────────────────────────────────────────
    # LLM Integration (Private Methods)
    # ──────────────────────────────────────────────

    def _get_cached_sentiment(self, pair: str, dataframe: DataFrame) -> str:
        """
        LLM 센티먼트를 캐시 기반으로 조회.

        캐시 TTL(4시간) 내이면 캐시 반환, 만료 시 LLM API 호출.
        LLM 장애 시 'neutral' 반환 (장애 격리 원칙).

        Args:
            pair: 거래 페어 (e.g., "BTC/USDT:USDT")
            dataframe: 현재 OHLCV 데이터

        Returns:
            "bullish", "bearish", "neutral" 중 하나
        """
        if not self._llm_enabled:
            return "neutral"

        now = int(time.time())
        cache_key = pair

        if cache_key in self._llm_cache:
            cached = self._llm_cache[cache_key]
            if now - cached["timestamp"] < self._llm_cache_ttl:
                return cached["sentiment"]

        # Call LLM API
        sentiment = self._call_llm_api(pair, dataframe)
        self._llm_cache[cache_key] = {
            "sentiment": sentiment,
            "timestamp": now,
        }

        return sentiment

    def _call_llm_api(self, pair: str, dataframe: DataFrame) -> str:
        """
        Claude API를 호출하여 시장 센티먼트 판단.

        입력: 최근 지표 요약 (~500 tokens)
        출력: {"sentiment": "bullish|bearish|neutral", "confidence": 0.0-1.0}

        Args:
            pair: 거래 페어
            dataframe: 현재 OHLCV + 지표 데이터

        Returns:
            "bullish", "bearish", "neutral" 중 하나. 에러 시 "neutral".
        """
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic package not installed. LLM filter disabled.")
            self._llm_enabled = False
            return "neutral"

        try:
            api_key = self._get_api_key()
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set. LLM filter disabled.")
                self._llm_enabled = False
                return "neutral"

            # Compress market data into minimal prompt (~500 tokens)
            market_summary = self._build_market_summary(pair, dataframe)

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Analyze this crypto futures market data and respond with ONLY "
                            f"a JSON object.\n\n{market_summary}\n\n"
                            f'Respond ONLY with: {{"sentiment": "bullish|bearish|neutral", '
                            f'"confidence": 0.0-1.0}}'
                        ),
                    }
                ],
            )

            result = json.loads(response.content[0].text)
            sentiment = result.get("sentiment", "neutral")

            if sentiment not in ("bullish", "bearish", "neutral"):
                return "neutral"

            logger.info(f"LLM sentiment for {pair}: {sentiment} (confidence: {result.get('confidence', 'N/A')})")
            return sentiment

        except Exception as e:
            logger.error(f"LLM API call failed for {pair}: {e}")
            return "neutral"

    def _build_market_summary(self, pair: str, dataframe: DataFrame) -> str:
        """
        LLM에 전달할 시장 데이터 요약 생성.

        최근 캔들의 주요 지표를 압축하여 ~500 토큰 이내로 구성.

        Args:
            pair: 거래 페어
            dataframe: 지표가 포함된 데이터프레임

        Returns:
            시장 요약 문자열
        """
        if dataframe.empty:
            return f"Pair: {pair}\nNo data available."

        last = dataframe.iloc[-1]
        prev_24h = dataframe.iloc[-288] if len(dataframe) > 288 else dataframe.iloc[0]
        price_change_24h = ((last["close"] - prev_24h["close"]) / prev_24h["close"]) * 100

        return (
            f"Pair: {pair}\n"
            f"Price: {last['close']:.4f}\n"
            f"24h Change: {price_change_24h:.2f}%\n"
            f"RSI(14): {last['rsi']:.1f}\n"
            f"BB Position: price {'below' if last['close'] < last['bb_lower'] else 'above' if last['close'] > last['bb_upper'] else 'within'} bands\n"
            f"BB Width: {last['bb_width']:.4f}\n"
            f"EMA Trend: {'bullish' if last['ema_9'] > last['ema_21'] > last['ema_50'] else 'bearish' if last['ema_9'] < last['ema_21'] < last['ema_50'] else 'mixed'}\n"
            f"MACD Histogram: {last['macdhist']:.4f}\n"
            f"Volume Ratio: {last['volume_ratio']:.2f}x avg\n"
            f"ATR(14): {last['atr']:.4f}\n"
        )

    def _get_api_key(self) -> Optional[str]:
        """
        ANTHROPIC_API_KEY를 환경변수에서 조회.

        Returns:
            API 키 문자열 또는 None
        """
        import os
        return os.environ.get("ANTHROPIC_API_KEY")
