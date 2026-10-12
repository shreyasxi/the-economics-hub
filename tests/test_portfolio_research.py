"""Independent analytically solvable research contracts; synthetic data only here."""
import unittest
import numpy as np
import pandas as pd
from data.processors.portfolio_analytics import simulate, risk_contributions
from data.processors.portfolio_attribution import attribute
from data.processors.portfolio_factors import fit, rolling, weekly_design, factor_shock, endpoints
from data.processors.portfolio_regimes import classify, conditional, DISCLOSURE
from data.fetchers.portfolio_macro import validate_series

class AttributionTests(unittest.TestCase):
    def test_compounding_and_classes(self):
        p=pd.DataFrame({'X':[100,110,121],'Y':[100,90,81]},index=pd.bdate_range('2020-01-01',periods=3))
        r=simulate(p,{'X':.5,'Y':.5}); a=attribute(p,r,{'X':'Equity','Y':'Bond'})
        np.testing.assert_allclose(a['contributions'],[.105,-.095,0],atol=1e-12)
        self.assertAlmostEqual(a['cumulative_return'],.01)
        self.assertAlmostEqual(a['classes']['Equity'],.105)
        np.testing.assert_allclose(a['daily'].sum(axis=1),r.returns,atol=1e-12)
        np.testing.assert_allclose(a['drift'],[.59900990099-.5,.40099009901-.5])
    def test_rebalancing_and_costs(self):
        p=pd.DataFrame({'X':[100,120,132],'Y':[100,100,90]},index=pd.to_datetime(['2020-01-30','2020-01-31','2020-02-03']))
        r=simulate(p,{'X':.5,'Y':.5},'Monthly',10); a=attribute(p,r)
        # First interval gains $1,000; rebalance costs 1,000*.001 = $1.
        self.assertAlmostEqual(a['cost'],1.)
        self.assertAlmostEqual(a['contributions']['X'],.154995)
        self.assertAlmostEqual(a['contributions']['Y'],-.054995)
        self.assertAlmostEqual(a['contributions']['Trading costs'],-.0001)
        self.assertAlmostEqual(a['contributions'].sum(),.0999)
    def test_many_assets(self):
        p=pd.DataFrame({str(i):[100,101,102] for i in range(40)},index=pd.bdate_range('2020-01-01',periods=3))
        a=attribute(p,simulate(p,{str(i):1/40 for i in range(40)}))
        self.assertAlmostEqual(a['contributions'].sum(),.02)
        with self.assertRaisesRegex(ValueError,'five times'):
            risk_contributions(p,{str(i):1/40 for i in range(40)})

class FactorTests(unittest.TestCase):
    def frame(self,n=312):
        t=np.arange(n); x=np.column_stack([np.sin(t*.7)*.03,np.cos(t*.3)*.002]); e=np.sin(t*1.3)*.001
        return pd.DataFrame({'Return':.001+x@np.array([.6,-4])+e,'Equity':x[:,0],'Rate':x[:,1]},index=pd.date_range('2010-01-01',periods=n,freq='W-FRI'))
    def test_ols_independent_matrix_and_hac(self):
        f=self.frame(); m=fit(f); x=np.column_stack([np.ones(len(f)),f[['Equity','Rate']]])
        expected=np.linalg.inv(x.T@x)@x.T@f.Return.to_numpy()
        np.testing.assert_allclose(m['table'].Coefficient,expected,rtol=1e-10)
        np.testing.assert_allclose(m['residual'],f.Return-x@expected,atol=1e-12)
        self.assertGreater(m['r_squared'],.99)
        self.assertTrue((m['table']['HAC standard error']>0).all())
        self.assertGreaterEqual(np.linalg.eigvalsh(m['covariance']).min(),-1e-15)
    def test_invalid_models(self):
        f=self.frame()
        for broken in [f.iloc[:50],f.assign(Rate=f.Equity),f.assign(Rate=f.Equity+f.Rate*1e-7),f.assign(Rate=np.nan)]:
            with self.assertRaises(ValueError):fit(broken)
    def test_rolling_no_future_and_units(self):
        f=self.frame(); r=rolling(f)
        self.assertFalse(r.empty)
        for _,row in r.iterrows():
            sample=f.loc[(f.index>row.Date-pd.Timedelta(weeks=104))&(f.index<=row.Date)]
            self.assertEqual(len(sample),104)
            self.assertAlmostEqual(row.Equity,fit(sample)['table'].loc['Equity','Coefficient'])
        m=fit(f); s=factor_shock(m,{'Equity':-.1,'Rate':.01})
        self.assertAlmostEqual(s['impact'],-.1*m['table'].loc['Equity','Coefficient']+.01*m['table'].loc['Rate','Coefficient'])
        with self.assertRaises(ValueError):factor_shock(m,{'Equity':-.1})
        with self.assertRaisesRegex(ValueError,'unsupported'):factor_shock(m,{'Equity':-1.,'Rate':1.})
    def test_frequency_missing_and_sign(self):
        dates=pd.bdate_range('2020-01-01','2020-03-06'); wealth=pd.Series(np.arange(len(dates))+100.,index=dates)
        rate=pd.Series(np.arange(len(dates))*.01+2,index=dates)
        f=weekly_design(wealth,wealth,{'DGS10':rate})
        self.assertAlmostEqual(f.Rate.iloc[0],.0005)
        self.assertAlmostEqual(f.Equity.iloc[0],5/102)
        missing=rate.drop(pd.Timestamp('2020-01-17'))
        g=weekly_design(wealth,wealth,{'DGS10':missing})
        self.assertNotIn(pd.Timestamp('2020-01-17'),g.index); self.assertNotIn(pd.Timestamp('2020-01-24'),g.index)
        partial,_=endpoints(wealth.iloc[:-1]); self.assertLess(partial.index[-1],pd.Timestamp('2020-03-06'))

class RegimeTests(unittest.TestCase):
    def macro(self):
        dates=pd.date_range('2000-01-01',periods=100,freq='MS')
        return {'CPIAUCSL':pd.Series(100*1.002**np.arange(100),index=dates),
                'CFNAIMA3':pd.Series(np.where(np.arange(100)%12<6,1.,-1.),index=dates)}
    def test_classification_not_trading_signal(self):
        m=self.macro(); c=classify(m)
        self.assertEqual(c.attrs['disclosure'],DISCLOSURE)
        self.assertEqual(c.Growth.iloc[0],'At/above trend'); self.assertEqual(c.Growth.iloc[6],'Below trend')
        self.assertTrue(c.Inflation.iloc[:15].isna().all())
        m['CPIAUCSL']=m['CPIAUCSL'].drop(m['CPIAUCSL'].index[20]); c=classify(m)
        self.assertTrue(pd.isna(c.Inflation.iloc[20])); self.assertTrue(pd.isna(c.Inflation.iloc[23]))
    def test_month_matching_episode_counts_and_small_samples(self):
        dates=pd.bdate_range('2000-01-01','2008-04-30'); p=pd.DataFrame({'X':100*1.0001**np.arange(len(dates))},index=dates)
        r=simulate(p,{'X':1}); c=classify(self.macro()); out=conditional({'A':r},c,'Growth')
        self.assertEqual(len(out['observations']),99)
        self.assertEqual(out['summary']['Distinct runs'].min(),8)
        vals,_=endpoints(r.wealth,'M'); expected=vals.pct_change(fill_method=None).iloc[1:]
        np.testing.assert_allclose(out['observations'].A,expected)
        short=conditional({'A':simulate(p.iloc[:80],{'X':1})},c,'Growth')
        self.assertTrue(short['summary']['Mean monthly return'].isna().all())
        c.attrs={}
        with self.assertRaises(ValueError):conditional({'A':r},c,'Growth')
    def test_macro_validation(self):
        m=self.macro()['CPIAUCSL']; validate_series(m,'CPIAUCSL')
        self.assertEqual(len(validate_series(m.drop(m.index[20]),'CPIAUCSL')),99)

class StressResearchTests(unittest.TestCase):
    def test_pre_during_post_samples_and_attribution(self):
        from unittest.mock import patch
        from data.processors.portfolio_stress import diversification_windows
        dates=pd.bdate_range('2018-01-01',periods=850); t=np.arange(len(dates))
        p=pd.DataFrame({'X':100*np.exp(.0001*t+.02*np.sin(t*.2)),'Y':100*np.exp(.00005*t+.01*np.cos(t*.3))},index=dates)
        episode=(str(dates[300].date()),str(dates[400].date()))
        with patch('data.processors.portfolio_stress.EPISODES',{'Test':episode}):
            s=diversification_windows(p,{'X':.6,'Y':.4},{'X':.3,'Y':.7},'X','Test')
        for label,expected in [('Pre-stress',252),('During stress (ex-post)',100),('Post-stress (ex-post)',252)]:
            est=s['estimates'][label]['Portfolio A']; self.assertEqual(est['observations'],expected)
            if label=='Pre-stress':self.assertLess(est['end'],dates[300])
            if label=='Post-stress (ex-post)':self.assertGreater(est['start'],dates[400])
            self.assertAlmostEqual(est['table']['Risk contribution'].sum(),1.)
        for n,a in s['attribution'].items():self.assertAlmostEqual(a['contributions'].sum(),s['summary'].loc['Episode return',n])
    def test_unavailable_and_inception(self):
        from unittest.mock import patch
        from data.processors.portfolio_stress import diversification_windows
        dates=pd.bdate_range('2020-01-01',periods=80); p=pd.DataFrame({'X':np.arange(80)+100.,'Y':np.arange(80)+200.},index=dates)
        with patch('data.processors.portfolio_stress.EPISODES',{'Test':(str(dates[10].date()),str(dates[50].date()))}):
            s=diversification_windows(p,{'X':1},{'Y':1},'X','Test')
            self.assertIn('Pre-stress',s['unavailable']);self.assertIn('Post-stress (ex-post)',s['unavailable'])
            p.loc[dates[:20],'Y']=np.nan
            with self.assertRaisesRegex(ValueError,'complete coverage'):diversification_windows(p,{'X':1},{'Y':1},'X','Test')
    def test_hac_independently_summed_scores(self):
        f=FactorTests().frame(120); m=fit(f); x=np.column_stack([np.ones(len(f)),f[['Equity','Rate']].to_numpy()]); e=m['residual'].to_numpy(); meat=np.zeros((3,3))
        scores=[x[i]*e[i] for i in range(len(f))]
        for score in scores:meat+=np.outer(score,score)
        for lag in range(1,5):
            for i in range(lag,len(f)):
                pair=np.outer(scores[i],scores[i-lag]);meat+=(1-lag/5)*(pair+pair.T)
        bread=np.linalg.inv(x.T@x); expected=bread@meat@bread*len(f)/(len(f)-3)
        np.testing.assert_allclose(m['covariance'],expected,atol=1e-12)

class MacroBundleTests(unittest.TestCase):
    def test_atomic_preparation_unit_contract_and_checksum(self):
        import tempfile
        from unittest.mock import patch
        from data.fetchers.portfolio_macro import prepare,load,current,SERIES
        def series(sid,period_years):
            freq=SERIES[sid][0]
            idx=pd.bdate_range(end=pd.Timestamp.now().normalize()-pd.Timedelta(days=1),periods=90) if freq=='daily' else pd.date_range(end=pd.Timestamp.now().normalize()-pd.offsets.MonthBegin(1),periods=30,freq='MS')
            return pd.Series(100+np.arange(len(idx))*.01,index=idx)
        with tempfile.TemporaryDirectory() as root, patch('data.fetchers.fred_fetcher.FredFetcher.fetch_series',side_effect=series):
            bundle=prepare(root); data,manifest=load(bundle)
            self.assertEqual(current(root),bundle)
            with patch('data.fetchers.fred_fetcher.FredFetcher.fetch_series',side_effect=ValueError('source failure')):
                with self.assertRaises(ValueError):prepare(root)
            self.assertEqual(current(root),bundle)
            (bundle/'DGS10.csv').write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):load(bundle)
    def test_hac_calendar_gaps(self):
        f=FactorTests().frame(140).drop(pd.Timestamp('2010-04-09')); model=fit(f)
        x=np.column_stack([np.ones(len(f)),f[['Equity','Rate']].to_numpy()]); e=model['residual'].to_numpy(); scores=x*e[:,None]
        meat=np.einsum('ni,nj->ij',scores,scores)
        for i,date in enumerate(f.index):
            for lag in range(1,5):
                prior=date-pd.Timedelta(weeks=lag)
                if prior in f.index:
                    j=f.index.get_loc(prior); cross=np.outer(scores[i],scores[j]);meat+=(1-lag/5)*(cross+cross.T)
        bread=np.linalg.inv(np.einsum('ni,nj->ij',x,x)); expected=np.einsum('ij,jk,kl->il',bread,meat,bread)*len(f)/(len(f)-3)
        np.testing.assert_allclose(model['covariance'],expected,atol=1e-12)
