"""Offline official-RBI excerpts; no internet required."""
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from data.fetchers.rbi_money_market import (
    BASE, RbiMoneyMarketError, collect, number, observation_date,
    parse_mmo, parse_policy, persist, read_rows, validate_row,
)
from charts.india_charts.india_monetary import crore_to_lakh_crore, liquidity_average, real_policy_data

FIXTURES = Path(__file__).parent/'fixtures/rbi_money_market'
URL = BASE+'BS_PressReleaseDisplay.aspx?prid=63742'


def fixture(name):
    return (FIXTURES/(name+'.html')).read_text()


def stored():
    row = parse_mmo(fixture('2026-10-07'), URL)
    policy = parse_policy(fixture('policy_2026'), URL)
    row.update({k: policy[k] for k in ('repo_rate','sdf_rate','msf_rate')})
    row['policy_source_url'] = URL
    return row


class MoneyMarketTests(unittest.TestCase):
    def test_five_manual_spot_checks(self):
        cases = [
            ('2025-05-26',(5.81,5.73,5.77),-169815.44,-204282),
            ('2025-01-19',(None,None,None),193847.49,-58628),
            ('2025-06-07',(None,None,None),-244926.14,-197212),
            ('2022-12-11',(None,None,None),-167943.15,-7277),
            ('2022-03-30',(3.27,3.38,3.34),-727306.80,-353466),
        ]
        for day, rates, total, today in cases:
            with self.subTest(day=day):
                row = parse_mmo(fixture(day), URL)
                self.assertEqual(tuple(row[k] for k in ('call_rate','treps_rate','market_repo_rate')),rates)
                self.assertEqual(row['date'],day)
                self.assertAlmostEqual(row['net_liquidity_injection_cr'],total)
                self.assertAlmostEqual(row['today_net_liquidity_injection_cr'],today)

    def test_indian_number_and_missing(self):
        self.assertEqual(number('1,93,847.49'),193847.49)
        self.assertEqual(number('193,847.49'),193847.49)
        self.assertEqual(number('−1,00,000'),-100000)
        self.assertEqual(number('0.00'),0)
        for text in ['-','',' ', '..']:
            self.assertIsNone(number(text))
        for text in ['nan','infinity','1,3,000','123oops']:
            with self.assertRaises(RbiMoneyMarketError): number(text)

    def test_observation_date_differs_from_publication(self):
        row=parse_mmo(fixture('2025-06-07'),URL)
        self.assertEqual(row['date'],'2025-06-07')
        self.assertEqual(row['release_date'],'2025-06-09')
        self.assertEqual(observation_date(fixture('2026-10-07')),date(2026,10,7))

    def test_policy_change_and_regime(self):
        old=parse_policy(fixture('policy_2025'),URL)
        new=parse_policy(fixture('policy_2026'),URL)
        introduction=parse_policy(fixture('policy_2022'),URL)
        self.assertEqual((old['sdf_rate'],old['repo_rate'],old['msf_rate']),(5,5.25,5.5))
        self.assertEqual((new['sdf_rate'],new['repo_rate'],new['msf_rate']),(5.25,5.5,5.75))
        self.assertEqual(introduction['date'],date(2022,4,8))
        row=stored();row['sdf_rate']=6
        with self.assertRaises(RbiMoneyMarketError): validate_row(row)
        row=stored();row['date']='2022-03-30'
        with self.assertRaises(RbiMoneyMarketError): validate_row(row)

    def test_units_and_sign(self):
        row=parse_mmo(fixture('2026-10-07'),URL)
        self.assertEqual(row['source_unit'],'crore')
        self.assertAlmostEqual(crore_to_lakh_crore(row['net_liquidity_injection_cr']),-4.2348082)
        self.assertEqual(crore_to_lakh_crore(100000),1)
        # Unit conversion branch only; this altered excerpt is not source data.
        billion=parse_mmo(fixture('2026-10-07').replace('₹ crore','₹ billion'),URL)
        self.assertAlmostEqual(billion['net_liquidity_injection_cr'],row['net_liquidity_injection_cr']*100)

    def test_zero_volume_never_a_market_rate(self):
        row=parse_mmo(fixture('2022-12-11'),URL)
        self.assertEqual(row['call_volume_cr'],0)
        self.assertIsNone(row['call_rate'])
        modified=fixture('2026-10-07').replace('13,337.07','0.00')
        self.assertIsNone(parse_mmo(modified,URL)['call_rate'])

    def test_malformed_and_challenge_fail(self):
        for html in ['','<p>CAPTCHA</p>',fixture('2026-10-07').replace('Call Money','Something Else'),fixture('2026-10-07').replace('₹ crore','USD'),fixture('2026-10-07').replace('-4,23,480.82','-')]:
            with self.assertRaises(RbiMoneyMarketError): parse_mmo(html,URL)
        with self.assertRaises(RbiMoneyMarketError): parse_mmo(fixture('2026-10-07'),'https://example.org/')

    def test_atomic_upsert_duplicates_and_corrections(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'canonical.csv'
            row=stored()
            self.assertEqual(persist([row,row],path),1)
            corrected=copy.deepcopy(row);corrected['release_date']='2026-10-09';corrected['call_rate']=5.4
            self.assertEqual(persist([corrected],path),1)
            persist([row],path)
            self.assertEqual(read_rows(path)[0]['call_rate'],5.4)
            before=path.read_bytes()
            invalid=copy.deepcopy(row);invalid['repo_rate']=10
            with self.assertRaises(RbiMoneyMarketError):persist([invalid],path)
            with self.assertRaises(RbiMoneyMarketError):persist([],path)
            self.assertEqual(path.read_bytes(),before)
            other=copy.deepcopy(row);other['date']='2026-10-06'
            persist([other],path)
            self.assertEqual([r['date'] for r in read_rows(path)],['2026-10-06','2026-10-07'])

    def test_empty_storage_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'empty.csv';path.write_text('')
            with self.assertRaises(RbiMoneyMarketError):read_rows(path)

    def test_effective_policy_change_no_old_rate_carry(self):
        class FakeClient:
            def archive(self,y,m):
                return {URL:'Resolution of the Monetary Policy Committee',
                        BASE+'BS_PressReleaseDisplay.aspx?prid=61749':'Resolution of the Monetary Policy Committee',
                        BASE+'BS_ViewMMO.aspx?prid=1':'Money Market Operations as on October 07, 2026'}
            def get(self,url):
                if url==URL:return fixture('policy_2026')
                if '61749' in url:return fixture('policy_2025')
                return fixture('2026-10-07')
        rows=collect(date(2026,10,7),date(2026,10,7),FakeClient())
        self.assertEqual(rows[0]['repo_rate'],5.5)

    def test_no_silent_empty_collection(self):
        class FakeClient:
            def archive(self,y,m):return {}
        with self.assertRaises(RbiMoneyMarketError):collect(date(2026,10,1),date(2026,10,7),FakeClient())

    def test_average_missing_weekday_is_not_filled(self):
        dates=pd.date_range('2026-08-01',periods=45,freq='D')
        frame=pd.DataFrame({'date':dates,'net_liquidity_injection_cr':100000.})
        trend=liquidity_average(frame)
        self.assertEqual(trend.dropna().iloc[-1],1)
        frame=frame[frame.date!=pd.Timestamp('2026-09-01')]
        self.assertTrue(pd.isna(liquidity_average(frame).iloc[-1]))

    def test_real_rate_uses_month_end_after_intra_month_hike(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sentinel.db'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE mpc_meetings(policy_cycle TEXT,repo_rate_pct REAL)')
                c.executemany('INSERT INTO mpc_meetings VALUES (?,?)',[('2026-08-05',5.25),('2026-10-07',5.5)])
            macro=pd.DataFrame({'date':pd.to_datetime(['2026-09-01','2026-10-01']),'india_cpi_yoy':[4.,4.]})
            status={'status':'ready','changes':[{'month':m,'column':'india_cpi_yoy','concept':'General','value':4.}
                                              for m in ('2026-09','2026-10')]}
            frame=real_policy_data(macro,path,status)
            self.assertEqual(frame.real_rate.tolist(),[1.25,1.5])
            macro.loc[0,'india_cpi_yoy']=1.
            with self.assertRaises(RbiMoneyMarketError):real_policy_data(macro,path,status)


if __name__=='__main__':unittest.main()
