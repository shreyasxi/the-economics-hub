"""Offline ranking, no-fill, provenance and fail-closed source mechanics."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import matplotlib.pyplot as plt
from data.processors import cpi_items as items, cpi_contributions as cpi
from charts.india_charts import india_cpi_items as chart
from data.fetchers import mospi_cpi_items as collector


def official(code, value, month='August', year='2026', index='100.00', name=None):
    return dict(base_year='2024', series='Current', year=year, month=month, state='All India',
                sector='Combined', division='Food and beverages', group='Food',
                **{'class':'Cereals and cereal products'}, sub_class='Cereals',
                item=name or 'Item '+str(code), code=f'01.1.1.1.1.{code:02d}',
                index=index, inflation=None if value is None else str(value), imputation='N')


def normalized(values, month='August',year='2026'):
    return items.normalize([official(i+1,v,month,year) for i,v in enumerate(values)], 'official-fixture')


class Ranking(unittest.TestCase):
    def test_latest_sign_order_limit_zero_missing(self):
        values = list(range(-10,11))+[None]
        rows = normalized(values)+normalized([99]*len(values),'July')
        data = items.snapshot(rows)
        self.assertEqual(data['latest_month'],'2026-08')
        self.assertEqual([r['yoy'] for r in data['increases']],list(range(10,2,-1)))
        self.assertEqual([r['yoy'] for r in data['declines']],list(range(-10,-2)))
        self.assertEqual(data['valid_count'],21)
        self.assertIn('August 2026',data['subtitle'])
        self.assertIn('Item 21 recorded the strongest increase at +10.0%',data['summary'])
        self.assertIn('Item 1 fell the most at −10.0%',data['summary'])

    def test_short_empty_and_zero_universe(self):
        for values, counts in [([1,-2,0,None],(1,1)),([1,2],(2,0)),([-1],(0,1)),([0,None],(0,0))]:
            data = items.snapshot(normalized(values))
            self.assertEqual((len(data['increases']),len(data['declines'])),counts)
            for side in ('increases','declines'):
                fig=chart.panel(data[side],side)
                self.assertEqual(len(fig.axes),1)
                self.assertEqual(len(fig.axes[0].patches),len(data[side]))
                fig.canvas.draw(); plt.close(fig)
            if not counts[1]: self.assertIn('no items recorded a decline',data['summary'])
            if not counts[0]: self.assertIn('no items recorded an increase',data['summary'])

    def test_duplicate_codes_fail_and_aggregates_excluded(self):
        r=official(1,2)
        with self.assertRaisesRegex(ValueError,'duplicate'): items.normalize([r,r],'x')
        aggregate=dict(r,item=None,code='01')
        self.assertEqual(len(items.normalize([r,aggregate],'x')),1)
        r['code']='01'
        with self.assertRaisesRegex(ValueError,'identity'): items.normalize([r],'x')

    def test_exact_same_base_derivation_no_fill(self):
        raw=[official(1,None,index='120'),official(1,None,year='2025',index='100')]
        rows=items.derive(items.normalize(raw,'source'))
        self.assertAlmostEqual(rows[0]['yoy'],20)
        self.assertEqual(rows[0]['yoy_method'],'derived')
        self.assertEqual(rows[0]['comparison_source_retrieval'],'source')
        self.assertIsNone(rows[1]['yoy'])
        items.validate(rows)
        other=items.normalize([official(1,None,year='2025',index='100')],'source')[0]
        other['base_year']='2012'
        with self.assertRaisesRegex(ValueError,'incompatible'): items.derive([items.normalize([raw[0]],'source')[0],other])
        for old in [official(2,None,year='2025'),official(1,None,year='2025',month='July'),official(1,None,year='2025',index=None)]:
            self.assertIsNone(items.derive(items.normalize([raw[0],old],'x'))[0]['yoy'])

    def test_missing_published_yoy_remains_missing_with_comparison_index(self):
        rows = items.normalize([official(1,None,index='120'), official(1,None,year='2025',index='100')], 'official')
        items.validate(rows)
        self.assertIsNone(rows[0]['yoy'])
        self.assertEqual(items.snapshot(rows)['valid_count'], 0)

    def test_provenance_extremes_and_missing_preserved(self):
        rows=normalized([999,-99,None])
        items.validate(rows)
        self.assertEqual(items.snapshot(rows)['increases'][0]['yoy'],999)
        self.assertEqual(rows[0]['source_url'],cpi.API_URL)
        self.assertEqual(rows[0]['yoy_method'],'published')
        self.assertEqual(rows[0]['imputation'],'N')
        changed=copy.deepcopy(rows); changed[0]['yoy']=5
        with self.assertRaisesRegex(ValueError,'provenance'): items.validate(changed)
        with self.assertRaisesRegex(ValueError,'partial'): items.validate(rows+normalized([1],'July'))

    def test_independent_axis_ranges_and_negative_direction(self):
        data=items.snapshot(normalized([80,-3]))
        figures=[chart.panel(data[s],s) for s in ('increases','declines')]
        self.assertGreater(figures[0].axes[0].get_xlim()[1],80)
        self.assertLess(figures[1].axes[0].get_xlim()[0],-3)
        self.assertEqual(figures[1].axes[0].get_xlim()[1],0)
        self.assertFalse(any(items.TITLE in t.get_text() for f in figures for t in f.texts))
        from matplotlib.colors import to_hex
        for fig, color in zip(figures, ('#e05458', '#30b080')):
            bar = fig.axes[0].patches[0]
            self.assertEqual(to_hex(bar.get_facecolor()), color)
            self.assertGreater(bar.get_linewidth(), 0)
            self.assertEqual(fig.texts[0].get_ha(), 'center')
            self.assertAlmostEqual(fig.texts[0].get_position()[0], (.49+.96)/2)
        for f in figures: plt.close(f)

    def test_official_historical_and_extreme_observations(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/cpi/official_items.json').read_text())
        items.validate(fixture)
        data = items.snapshot(fixture)
        self.assertEqual(data['increases'][0]['item_name'], 'Silver jewellery')
        self.assertEqual(data['increases'][0]['yoy'], 107.11)
        self.assertEqual(data['declines'][0]['item_name'], 'Tomato')
        self.assertEqual(data['declines'][0]['yoy'], -31.09)
        self.assertEqual(len({r['month_key'] for r in fixture}), 3)
        for r in fixture:
            if r['month_key'] == '2026-08':
                prior = next(p for p in fixture if p['month_key'] == '2025-08' and p['item_code'] == r['item_code'])
                # Both published indices and YoY are rounded to two decimals.
                lower = ((r['index_level']-.005)/(prior['index_level']+.005)-1)*100-.005
                upper = ((r['index_level']+.005)/(prior['index_level']-.005)-1)*100+.005
                self.assertLessEqual(lower, r['yoy'])
                self.assertLessEqual(r['yoy'], upper)

    def test_generation_both_panels_and_failure_removes_assets(self):
        with tempfile.TemporaryDirectory() as d:
            for values in ([1,-2], [1,2], [-2], [0,None]):
                with patch.object(items,'load_current',return_value=(normalized(values),dict(run_id='x',coverage_start='2026-08'))):
                    self.assertEqual(len(chart.generate(d)),2)
                    self.assertEqual(len(list(Path(d).glob('*.png'))),2)
            with patch.object(items,'load_current',side_effect=ValueError('failed source')):
                self.assertEqual(chart.generate(d),[])
                self.assertEqual(list(Path(d).iterdir()),[])

    def test_failed_refresh_preserves_pointer_and_closes_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'current.json').write_text('{"run_id":"prior"}')
            before=(root/'current.json').read_bytes()
            with patch.object(items,'load_current',return_value=(normalized([1]),{})), patch.object(collector,'discover_latest',side_effect=ValueError('offline')):
                with self.assertRaises(ValueError): collector.update(root,session=object())
            self.assertEqual(before,(root/'current.json').read_bytes())
            self.assertEqual(json.loads((root/'last_attempt.json').read_text())['status'],'failed')
            self.assertFalse((root/'.update.lock').exists())


if __name__ == '__main__': unittest.main()
