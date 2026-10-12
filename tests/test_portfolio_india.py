"""Independent economic invariants, timestamp safety and India integration."""
import unittest
import numpy as np
import pandas as pd
from data.processors.portfolio_currency import asof_values,h10_availability,decomposition,weekly_reference_panel,import_growth_nav,portfolio_fx_pnl
from data.processors.portfolio_sip import xirr,contributions,sip
from data.processors.portfolio_analytics import simulate,compare,metrics,risk_contributions
from data.processors.portfolio_attribution import attribute


class CurrencyTests(unittest.TestCase):
    def test_portfolio_fx_pnl_with_actual_entering_holdings(self):
        dates=pd.date_range('2020-01-01',periods=2)
        local=pd.DataFrame({'SPY':[100.,110.],'INR':[100.,100.]},index=dates)
        fx=pd.Series([70.,77.],index=dates);prices=local.copy();prices['SPY']*=fx
        result=simulate(prices,{'SPY':.4,'INR':.6},initial=100000)
        parts=portfolio_fx_pnl(prices,local,fx,result,{'SPY':{'currency':'USD'},'INR':{'currency':'INR'}})
        self.assertAlmostEqual(parts['Foreign market'],.04);self.assertAlmostEqual(parts['Currency'],.04)
        self.assertAlmostEqual(parts['Interaction'],.004);self.assertAlmostEqual(parts.sum(),.084)
    def test_exact_currency_direction_and_interaction(self):
        d=pd.date_range('2020-01-01',periods=2)
        local=pd.DataFrame({'SPY':[100.,110.]},index=d);fx=pd.Series([70.,77.],index=d)
        parts=decomposition(local,fx)
        self.assertAlmostEqual(parts.loc['SPY','Foreign asset'],.1)
        self.assertAlmostEqual(parts.loc['SPY','Currency'],.1)
        self.assertAlmostEqual(parts.loc['SPY','Interaction'],.01)
        self.assertAlmostEqual(parts.loc['SPY','Total INR'],.21)
        self.assertLess(decomposition(local,pd.Series([70.,63.],index=d)).loc['SPY','Total INR'],.1)

    def test_no_us_future_close_or_double_conversion(self):
        dates=pd.bdate_range('2020-01-01',periods=24)
        histories={'nifty-50':pd.Series(100+np.arange(24),index=dates),'US':pd.Series(200+np.arange(24),index=dates)}
        meta={'nifty-50':{'currency':'INR'},'US':{'currency':'USD'}};fx=pd.Series(70.,index=dates)
        panel,local,marks,evidence=weekly_reference_panel(histories,meta,fx)
        np.testing.assert_allclose(panel['nifty-50'],local['nifty-50'])
        np.testing.assert_allclose(panel.US,local.US*marks,equal_nan=True)
        self.assertTrue((evidence.available_utc.dropna()<=evidence.loc[evidence.available_utc.notna(),'checkpoint_utc']).all())
        day=panel.index[-1];before=histories['US'].copy();before.loc[day:]*=100
        changed=weekly_reference_panel(dict(histories,US=before),meta,fx)[0]
        self.assertEqual(panel.loc[day,'US'],changed.loc[day,'US'])

    def test_fx_release_holiday_and_missing_source(self):
        release=h10_availability(pd.DatetimeIndex(['2020-01-17']))[0]
        # MLK Monday holiday shifts scheduled release to Tuesday 16:15 NY.
        self.assertEqual(release,pd.Timestamp('2020-01-21 21:15',tz='UTC'))
        s=pd.Series([70.],index=pd.DatetimeIndex(['2020-01-17']))
        marks,_=asof_values(s,[release],pd.DatetimeIndex(['2020-01-21 10:00','2020-01-22 10:00','2020-02-20 10:00'],tz='UTC'),12)
        self.assertTrue(np.isnan(marks[0]));self.assertEqual(marks[1],70);self.assertTrue(np.isnan(marks[2]))
        with self.assertRaises(ValueError):asof_values(s*float('nan'),[release],pd.DatetimeIndex([release]),12)

    def test_nav_identity_and_permission_gate(self):
        frame=pd.DataFrame({'date':['2020-01-02','2020-01-03'],'scheme_code':['1','1'],'isin':['ABC','ABC'],'nav':[10.,11.]})
        identity=dict(scheme_code='1',isin='ABC',amc='AMC',name='Fund',plan='Direct',option='Growth',inception='2020-01-01',currency='INR',permission='Licensed local file',continuity_verified=True)
        self.assertEqual(len(import_growth_nav(frame,identity)),2)
        for bad in [dict(identity,option='IDCW'),dict(identity,plan='Regular'),dict(identity,permission=''),dict(identity,inception='2020-02-01')]:
            with self.assertRaises(ValueError):import_growth_nav(frame,bad)
        frame.loc[1,'isin']='DIFFERENT'
        with self.assertRaises(ValueError):import_growth_nav(frame,identity)


class SIPTests(unittest.TestCase):
    def test_contributions_can_stop_before_terminal_valuation(self):
        dates=pd.date_range('2020-01-01','2020-06-24',freq='W-WED')
        prices=pd.DataFrame({'A':10.},index=dates);prices.attrs['max_gap_days']=14
        result=sip(prices,{'A':1},'2020-01-01','2020-03-31',100.,valuation_end='2020-06-24',cost_bps=0)
        self.assertEqual(result['invested'].iloc[-1],300)
        self.assertEqual(result['wealth'].index[-1],pd.Timestamp('2020-06-24'))
        self.assertAlmostEqual(result['xirr']['value'],0,places=10)
        with self.assertRaises(ValueError):sip(prices,{'A':1},'2019-01-01','2020-03-31',100)
    def test_units_capital_gain_and_flow_removed_return(self):
        dates=pd.DatetimeIndex(['2020-01-02','2020-02-03','2020-03-02'])
        prices=pd.DataFrame({'A':[10.,20.,40.]},index=dates);prices.attrs['max_gap_days']=14
        # Unit case uses weekly grid and monthly contributions.
        dates=pd.date_range('2020-01-01','2020-03-04',freq='W-WED')
        prices=pd.DataFrame({'A':[10. if d.month==1 else 20. if d.month==2 else 40. for d in dates]},index=dates);prices.attrs['max_gap_days']=14
        result=sip(prices,{'A':1},'2020-01-01','2020-03-04',100.,cost_bps=0)
        self.assertEqual(result['invested'].iloc[-1],300.)
        self.assertAlmostEqual(result['units'].iloc[-1,0],17.5)
        self.assertAlmostEqual(result['wealth'].iloc[-1],700.)
        self.assertAlmostEqual(result['gain'].iloc[-1],400.)
        self.assertAlmostEqual(result['twr'].iloc[-1],4.)
        self.assertEqual(result['flows']['Investment date'].iloc[1],pd.Timestamp('2020-02-05'))

    def test_known_xirr_and_ambiguous_flows(self):
        dates=pd.DatetimeIndex(['2021-01-01','2022-01-01'])
        self.assertAlmostEqual(xirr(pd.Series([-100.,110.],index=dates))['value'],.1,places=10)
        self.assertIsNone(xirr(pd.Series([100.,110.],index=dates))['value'])
        self.assertIsNone(xirr(pd.Series([-100.,230.,-132.],index=pd.date_range('2020-01-01',periods=3,freq='YS')))['value'])
        with self.assertRaises(ValueError):contributions(dates,'2021-01-01','2021-02-01',-1)

    def test_rebalance_cost_and_arbitrary_holdings(self):
        dates=pd.date_range('2020-01-01',periods=80,freq='W-WED')
        prices=pd.DataFrame({str(k):100*np.power(1+.001*k,np.arange(80)) for k in range(8)},index=dates);prices.attrs['max_gap_days']=14
        weights={str(k):1/8 for k in range(8)}
        base=simulate(prices,weights,'Monthly',5,100000)
        self.assertAlmostEqual(attribute(prices,base)['contributions'].sum(),base.wealth.iloc[-1]/100000-1)
        flow=sip(prices,weights,dates[0],dates[-1],1000,100000,rebalancing='Monthly',cost_bps=5)
        self.assertGreater(flow['trades'].Cost.sum(),0)
        self.assertTrue(np.allclose(flow['wealth'],flow['holdings'].sum(axis=1)))
        self.assertGreater(flow['purchase_cost'],0)
        with self.assertRaises(ValueError):sip(prices,weights,dates[0],dates[-1],1000,cost_bps=-1)


class RealIndiaTests(unittest.TestCase):
    def test_real_instrument_data_and_shared_analytics(self):
        from data.fetchers.portfolio_india import current,load
        try:p,local,fx,m=load(current())
        except OSError:self.skipTest('Private INR snapshot unavailable')
        self.assertEqual(len(m['assets']),12)
        self.assertEqual(m['assets']['nifty-50']['return_convention'],'Official gross total-return index')
        self.assertEqual(m['assets']['GILT5YBEES.NS']['currency'],'INR')
        a={'NIFTYBEES.NS':.6,'GILT5YBEES.NS':.4}
        common,r=compare(p,a,a,'nifty-50',initial=100000)
        self.assertEqual(r['Portfolio A'].wealth.iloc[0],100000)
        self.assertIn('Final wealth (₹)',metrics(r['Portfolio A'],52,'₹'))
        self.assertAlmostEqual(risk_contributions(common,a,52,52)['table']['Risk contribution'].sum(),1.)
        from data.processors.portfolio_india_regimes import cpi_history,policy_history,factor_design
        cpi=cpi_history();self.assertTrue(pd.isna(cpi.loc[pd.Period('2026-01'),'Change']))
        self.assertFalse(policy_history().index.duplicated().any())
        from data.processors.portfolio_factors import fit
        model=fit(factor_design(r['Portfolio A'].wealth,p['nifty-50'],fx))
        self.assertGreaterEqual(model['observations'],104)
