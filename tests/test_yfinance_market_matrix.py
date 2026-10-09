"""Explicit Yahoo return paths must not alter generic chart fetch semantics."""
from unittest.mock import Mock
import pandas as pd
import pytest
from config.market_matrix import ADJUSTED_TOTAL_RETURN, DIRECT_PRICE_RETURN
from data.fetchers.yfinance_fetcher import YFinanceFetcher


@pytest.fixture
def ticker(monkeypatch):
    import data.fetchers.yfinance_fetcher as mod
    tk=Mock();tk.history.return_value=pd.DataFrame({'Close':[10.,11.], 'Adj Close':[5.,6.]})
    monkeypatch.setattr(mod.yf,'Ticker',lambda _:tk)
    monkeypatch.setattr(mod.time,'sleep',lambda _:None)
    return tk


def test_adjusted_return_explicit(ticker):
    s=YFinanceFetcher().get_total_return_series('SPY')
    assert list(s)==[5.,6.] and s.attrs['return_method']==ADJUSTED_TOTAL_RETURN
    ticker.history.assert_called_once_with(period='max',interval='1d',auto_adjust=False,actions=True)


def test_no_adjusted_fallback(ticker):
    ticker.history.return_value=pd.DataFrame({'Close':[10.]})
    with pytest.raises(ValueError,match='adjusted-close'):YFinanceFetcher().get_total_return_series('SPY')


def test_bitcoin_direct_close(ticker):
    s=YFinanceFetcher().get_price_return_series('BTC-USD')
    assert list(s)==[10.,11.] and s.attrs['return_method']==DIRECT_PRICE_RETURN
    ticker.history.assert_called_once_with(period='max',interval='1d',auto_adjust=False,actions=True)


def test_generic_chart_calls_unchanged(ticker):
    assert list(YFinanceFetcher().get_close_series('SPY'))==[10.,11.]
    ticker.history.assert_called_once_with(period='1y',interval='1d')
