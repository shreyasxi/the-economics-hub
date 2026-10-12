"""Economic invariants of the mixed calendar and oil corporate actions."""
import unittest
import numpy as np
import pandas as pd
from data.fetchers.portfolio_bitcoin import validate_bitcoin, align_bitcoin
from data.fetchers.portfolio_prices import validate_history, load_bundle,snapshot_path
from data.processors.portfolio_analytics import simulate,compare,risk_contributions
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_stress import historical_replay,hypothetical_shock


def btc_fixture(start='2020-01-01',periods=10):
    return pd.DataFrame({'asset':'btc','time':pd.date_range(start,periods=periods,tz='UTC'),
                         'PriceUSD':100*np.power(1.01,np.arange(periods))})


class CalendarTests(unittest.TestCase):
    def test_prior_fixing_no_future_match_and_weekend_compounding(self):
        raw=btc_fixture('2020-01-02',8)
        dates=pd.DatetimeIndex(['2020-01-03','2020-01-06','2020-01-07'])
        btc,evidence=align_bitcoin(raw,dates)
        self.assertEqual(btc.iloc[0],100)
        self.assertAlmostEqual(btc.iloc[1]/btc.iloc[0]-1,1.01**3-1)
        self.assertTrue((evidence.fixing_utc<evidence.valuation_utc).all())
        future=raw.copy();future.loc[future.time>=pd.Timestamp('2020-01-07',tz='UTC'),'PriceUSD']*=10
        pd.testing.assert_series_equal(btc,align_bitcoin(future,dates)[0])
        self.assertEqual(len(validate_bitcoin(raw)),8)  # raw weekends retained

    def test_utc_dst_offsets_and_missing_fixings(self):
        dates=pd.DatetimeIndex(['2020-03-06','2020-03-09'])
        _,ev=align_bitcoin(btc_fixture('2020-03-05',6),dates)
        self.assertEqual(ev.valuation_utc.iloc[0].hour,21)
        self.assertEqual(ev.valuation_utc.iloc[1].hour,20)
        raw=btc_fixture()
        for broken in [raw.drop(index=3),pd.concat([raw,raw.iloc[-1:]]),raw.assign(PriceUSD=-1),raw.assign(asset='eth')]:
            with self.assertRaises(ValueError):validate_bitcoin(broken)
        bad=raw.copy();bad['time']=bad.time+pd.Timedelta(hours=1)
        with self.assertRaises(ValueError):validate_bitcoin(bad)
        encoded=raw.copy();encoded['time']=encoded.time.map(lambda t:t.tz_convert('Asia/Kolkata').isoformat())
        pd.testing.assert_frame_equal(validate_bitcoin(encoded),validate_bitcoin(raw))
        naive=raw.copy();naive['time']=naive.time.dt.tz_localize(None)
        with self.assertRaises(ValueError):validate_bitcoin(naive)

    def test_no_pre_history_or_carried_final_fixing(self):
        dates=pd.bdate_range('2019-12-30','2020-01-15')
        series,_=align_bitcoin(btc_fixture(),dates)
        self.assertTrue(series.loc[:'2020-01-01'].isna().all())
        self.assertTrue(series.loc['2020-01-13':].isna().all())
        self.assertEqual(series.first_valid_index(),pd.Timestamp('2020-01-02'))

    def test_month_end_rebalance_correct_mixed_calendar(self):
        dates=pd.bdate_range('2020-01-01','2020-03-10')
        btc,_=align_bitcoin(btc_fixture('2019-12-31',80),dates)
        frame=pd.DataFrame({'BTC':btc,'SPY':100.,'USO':80*np.power(.999,np.arange(len(dates)))},index=dates)
        weights={'BTC':.2,'SPY':.6,'USO':.2}
        result=simulate(frame,weights,'Monthly',5)
        ledger=attribute(frame,result)
        self.assertAlmostEqual(ledger['contributions'].sum(),result.wealth.iloc[-1]/10000-1,places=10)
        self.assertEqual(list(result.trades.date),[pd.Timestamp('2020-01-31'),pd.Timestamp('2020-02-28')])
        for d in result.trades.date:
            np.testing.assert_allclose(result.weights.loc[d],list(weights.values()),rtol=1e-12)
        risk=risk_contributions(frame,weights)
        daily=frame[list(weights)].pct_change(fill_method=None).iloc[1:]
        w=np.array(list(weights.values()));cov=daily.cov().to_numpy()*252
        self.assertAlmostEqual(risk['variance'],w@cov@w)
        self.assertAlmostEqual(risk['table']['Risk contribution'].sum(),1)
        impact,parts=hypothetical_shock(weights,{'BTC':-.5,'SPY':-.2,'USO':.3})
        self.assertAlmostEqual(impact,-.16)
        self.assertAlmostEqual(parts.sum(),impact)


class OilTests(unittest.TestCase):
    def test_split_adjusted_prices_preserve_return(self):
        dates=pd.bdate_range('2020-04-27',periods=4)
        # Both Yahoo Close and Adj Close are already split-adjusted.
        frame=pd.DataFrame({'Close':[16.,16.4,17.1,18.], 'Adj Close':[16.,16.4,17.1,18.],
                            'Dividends':0.,'Stock Splits':[0.,0.,.125,0.]},index=dates)
        validated,_=validate_history('USO',frame)
        self.assertAlmostEqual(validated['Adj Close'].pct_change().loc['2020-04-29'],17.1/16.4-1)
        for broken in [frame.assign(**{'Stock Splits':0}),frame.assign(**{'Close':[2.,2.05,17.1,18.],'Adj Close':[2.,2.05,17.1,18.]})]:
            with self.assertRaises(ValueError):validate_history('USO',broken)

    def test_real_source_invariants_and_episode_availability(self):
        try:prices,manifest=load_bundle(snapshot_path())
        except (ValueError,OSError):self.skipTest('Prepared source evidence unavailable')
        if not {'BTC','USO'}.issubset(prices):self.skipTest('Expansion snapshot unavailable')
        self.assertEqual(manifest['assets']['USO']['first_observation'],'2006-04-10')
        self.assertEqual(manifest['assets']['BTC']['raw_first_label'][:10],'2010-07-18')
        self.assertTrue(prices.loc[:'2010-07-16','BTC'].isna().all())
        self.assertTrue(prices.loc[:'2006-04-07','USO'].isna().all())
        with self.assertRaisesRegex(ValueError,'BTC lacks complete coverage'):
            historical_replay(prices,{'BTC':.1,'SPY':.9},{'SPY':1},'SPY','Global Financial Crisis')
        common,results,_,_=historical_replay(prices,{'BTC':.1,'USO':.2,'SPY':.7},{'SPY':1},'SPY','COVID-19 Market Shock','Monthly',5)
        for r in results.values():self.assertTrue((r.wealth>0).all())
        uso=prices.USO.dropna()
        self.assertLess(abs(uso.pct_change(fill_method=None).loc['2020-04-29']),.5)
        self.assertLess(uso.loc['2020-04-30']/uso.loc['2020-02-19']-1,-.5)
        weights={t:1/len(prices.columns) for t in prices}
        full,r=compare(prices,weights,weights)
        self.assertTrue(full.notna().all().all())
        pd.testing.assert_series_equal(r['Portfolio A'].wealth,r['Portfolio B'].wealth)
