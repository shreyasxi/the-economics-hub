"""Offline daily pipeline scenarios: overlap, no-op, revision and fail-closed publish."""
import copy
import csv
import os
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

from charts.india_charts import india_monetary as charts
from data.fetchers import rbi_money_market as rbi

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures/rbi_money_market'
PNG = b'\x89PNG\r\n\x1a\n'


def observation(day='2026-10-07'):
    url = rbi.BASE+'BS_PressReleaseDisplay.aspx?prid=63742'
    row = rbi.parse_mmo((FIXTURES/'2026-10-07.html').read_text(), url,
                        fetched_at='2026-10-08T12:00:00+00:00')
    policy = rbi.parse_policy((FIXTURES/'policy_2026.html').read_text(), url)
    row.update({k:policy[k] for k in ('repo_rate','sdf_rate','msf_rate')})
    row['policy_source_url'] = url
    row['date'] = day
    row['release_date'] = (date.fromisoformat(day)+timedelta(days=1)).isoformat()
    return row


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root/'canonical.csv'
        self.rows = [observation((date(2026,9,25)+timedelta(days=i)).isoformat()) for i in range(13)]
        rbi.persist(self.rows,self.csv)
        self.assets = self.root/'assets'
        self.edition = self.assets/'india/2026-10'
        self.edition.mkdir(parents=True)
        (self.assets/'india/2026-09').mkdir()
        (self.assets/'india/not-an-edition').mkdir()
        for name in (charts.WACR_SPREAD,charts.LIQUIDITY,'06_india_inflation_bar.png','soe.json'):
            (self.edition/name).write_bytes(b'original '+name.encode())

    def snapshot(self):
        return {str(p.relative_to(self.root)):p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts}

    def render(self, name):
        def fake(frame, output):
            target = Path(output)/name
            target.write_bytes(PNG+str(frame.call_rate.iloc[-1]).encode())
            return target
        return fake

    def pipeline(self, rows):
        with patch.object(rbi,'collect',return_value=rows) as fetch, \
             patch.object(charts,'wacr_spread',side_effect=self.render(charts.WACR_SPREAD)) as w, \
             patch.object(charts,'liquidity',side_effect=self.render(charts.LIQUIDITY)) as l:
            changed = rbi.refresh_recent(self.csv,today=date(2026,10,9))
            if changed:
                charts.refresh_current(self.csv,self.assets)
            return changed,fetch,w,l

    def test_scenario_a_new_observation_only_three_files_change(self):
        before = self.snapshot()
        new = observation('2026-10-08')
        changed,fetch,w,l = self.pipeline(self.rows[-10:]+[new])
        self.assertTrue(changed)
        self.assertEqual(fetch.call_args.args,(date(2026,9,28),date(2026,10,9)))
        self.assertEqual(rbi.read_rows(self.csv)[-1]['date'],'2026-10-08')
        w.assert_called_once(); l.assert_called_once()
        after = self.snapshot()
        self.assertEqual({k for k in after if before.get(k)!=after[k]},
                         {'canonical.csv',f'assets/india/2026-10/{charts.WACR_SPREAD}',
                          f'assets/india/2026-10/{charts.LIQUIDITY}'})

    def test_scenario_b_no_new_release_is_byte_identical_and_no_chart_churn(self):
        before = self.snapshot()
        rows = copy.deepcopy(self.rows[-10:])
        for row in rows:
            row['fetched_at'] = '2026-10-09T12:00:00+00:00'
        changed,_,w,l = self.pipeline(rows)
        self.assertFalse(changed)
        w.assert_not_called(); l.assert_not_called()
        self.assertEqual(self.snapshot(),before)

    def test_noop_has_no_git_diff(self):
        def git(*args):
            return subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True,text=True)
        git('init','-q')
        git('add','.')
        # The index is the synthetic baseline; no commit is needed or created.
        self.pipeline(copy.deepcopy(self.rows[-10:]))
        git('diff','--exit-code')
        self.assertEqual(git('diff','--name-only').stdout,'')
        self.assertEqual(git('ls-files','--others','--exclude-standard').stdout,'')

    def test_scenario_c_bad_source_and_empty_fetch_preserve_csv_and_live_charts(self):
        for response in (rbi.RbiMoneyMarketError('RBI source unavailable'),
                         rbi.RbiMoneyMarketError('RBI challenge/error page'), []):
            before = self.snapshot()
            with patch.object(rbi,'collect',side_effect=response if isinstance(response,Exception) else None,
                              return_value=response), \
                 patch.object(charts,'wacr_spread') as w:
                with self.assertRaises(rbi.RbiMoneyMarketError):
                    rbi.refresh_recent(self.csv,today=date(2026,10,9))
                w.assert_not_called()
            self.assertEqual(self.snapshot(),before)

    def test_scenario_d_revision_replaces_same_date_and_renders_both(self):
        revised = observation()
        revised['call_rate'] = 5.4
        revised['release_date'] = '2026-10-09'
        revised['fetched_at'] = '2026-10-09T12:00:00+00:00'
        changed,_,w,l = self.pipeline([revised])
        self.assertTrue(changed)
        result = rbi.read_rows(self.csv)
        self.assertEqual(len(result),len(self.rows))
        self.assertEqual(result[-1]['call_rate'],5.4)
        self.assertEqual(result[-1]['date'],'2026-10-07')
        w.assert_called_once(); l.assert_called_once()
        older = observation()
        rbi.persist([older],self.csv)
        self.assertEqual(rbi.read_rows(self.csv)[-1]['call_rate'],5.4)

    def test_positive_volume_missing_wacr_and_missing_repo_fail_before_replace(self):
        for field in ('call_rate','repo_rate'):
            bad = observation(); bad[field] = None
            before = self.csv.read_bytes()
            with patch.object(rbi,'collect',return_value=[bad]):
                with self.assertRaises(rbi.RbiMoneyMarketError):
                    rbi.refresh_recent(self.csv,today=date(2026,10,9))
            self.assertEqual(self.csv.read_bytes(),before)

    def test_atomic_candidate_write_failure_preserves_canonical(self):
        before = self.csv.read_bytes()
        with patch.object(rbi,'collect',return_value=[observation('2026-10-08')]), \
             patch.object(rbi.os,'replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                rbi.refresh_recent(self.csv,today=date(2026,10,9))
        self.assertEqual(self.csv.read_bytes(),before)

    def test_staleness_warning_at_four_days_failure_after_seven(self):
        with patch('builtins.print') as warning:
            rbi.check_staleness(self.rows,date(2026,10,11))
        self.assertIn('::warning::',warning.call_args.args[0])
        before = self.snapshot()
        with patch.object(rbi,'collect',return_value=[observation()]):
            with self.assertRaisesRegex(rbi.RbiMoneyMarketError,'stale by 8'):
                rbi.refresh_recent(self.csv,today=date(2026,10,15))
        self.assertEqual(self.snapshot(),before)

    def test_latest_never_moves_backwards_when_recent_release_is_missing(self):
        with patch.object(rbi,'collect',return_value=self.rows[-10:-1]):
            self.assertFalse(rbi.refresh_recent(self.csv,today=date(2026,10,9)))
        self.assertEqual(rbi.read_rows(self.csv)[-1]['date'],'2026-10-07')

    def test_unsorted_or_duplicate_canonical_dates_fail_closed(self):
        for rows in (list(reversed(self.rows)),self.rows+[self.rows[-1]]):
            with self.csv.open('w',newline='') as out:
                writer = csv.DictWriter(out,fieldnames=rbi.COLUMNS)
                writer.writeheader(); writer.writerows(rows)
            before = self.csv.read_bytes()
            with self.assertRaises(rbi.RbiMoneyMarketError):
                rbi.read_rows(self.csv)
            self.assertEqual(self.csv.read_bytes(),before)

    def test_active_edition_matches_production_loader_and_does_not_create_month(self):
        from charts import loader
        with patch.object(loader,'_get_base_dirs',return_value=[self.assets]):
            # The loader sorts all folders; use valid edition folders here.
            (self.assets/'india/not-an-edition').rmdir()
            self.assertEqual(charts.active_india_edition(self.assets),loader._latest_folder('india')[0])
        self.assertEqual(charts.active_india_edition(self.assets),self.edition)
        with self.assertRaises(rbi.RbiMoneyMarketError):
            charts.active_india_edition(self.assets/'india')

    def test_second_chart_failure_preserves_both_live_assets(self):
        before = self.snapshot()
        with patch.object(charts,'wacr_spread',side_effect=self.render(charts.WACR_SPREAD)), \
             patch.object(charts,'liquidity',side_effect=RuntimeError('render failed')):
            with self.assertRaises(RuntimeError):
                charts.refresh_current(self.csv,self.assets)
        self.assertEqual(self.snapshot(),before)

    def test_second_asset_replace_failure_rolls_back_first(self):
        before = self.snapshot()
        replace = os.replace
        def fail_second(source,target):
            if Path(source).name == charts.LIQUIDITY:
                raise OSError('second replacement failed')
            return replace(source,target)
        with patch.object(charts,'wacr_spread',side_effect=self.render(charts.WACR_SPREAD)), \
             patch.object(charts,'liquidity',side_effect=self.render(charts.LIQUIDITY)), \
             patch.object(charts.os,'replace',side_effect=fail_second):
            with self.assertRaises(OSError):
                charts.refresh_current(self.csv,self.assets)
        self.assertEqual(self.snapshot(),before)

    def test_valid_empty_current_month_archive_is_allowed_but_empty_history_fails(self):
        today = rbi.datetime.now(rbi.ZoneInfo('Asia/Kolkata')).date()
        client = rbi.Client()
        def html(year,month):
            return (f'<input type="hidden" name="__VIEWSTATE" value="ok">'
                    f'<input type="hidden" name="__EVENTVALIDATION" value="ok">'
                    f'<input type="hidden" name="hdnYear" value="{year}">'
                    f'<input type="hidden" name="hdnMonth" value="{month}">')
        response = Mock(url=rbi.BASE+'BS_PressReleaseDisplay.aspx')
        response.text = html(today.year,today.month)
        with patch.object(client,'get',return_value=response.text), \
             patch.object(client.session,'post',return_value=response):
            self.assertEqual(client.archive(today.year,today.month),{})
            old = today.replace(day=1)-timedelta(days=1)
            response.text = html(old.year,old.month)
            with self.assertRaisesRegex(rbi.RbiMoneyMarketError,'No MMO releases'):
                client.archive(old.year,old.month)

    def test_real_targeted_generation_exactly_two_pngs_preserves_other_assets(self):
        before = self.snapshot()
        paths = charts.refresh_current(self.csv,self.assets)
        self.assertEqual({p.name for p in paths},{charts.WACR_SPREAD,charts.LIQUIDITY})
        for path in paths:
            self.assertTrue(path.read_bytes().startswith(PNG))
        after = self.snapshot()
        self.assertEqual(after['canonical.csv'],before['canonical.csv'])
        for name in ('06_india_inflation_bar.png','soe.json'):
            key = f'assets/india/2026-10/{name}'
            self.assertEqual(after[key],before[key])
        self.assertFalse(list(self.edition.glob('.monetary-render-*')))

    def test_workflow_contracts_shared_lock_unchanged_saturday_schedule_and_no_services(self):
        daily = (ROOT/'.github/workflows/rbi_monetary_conditions.yml').read_text()
        saturday = (ROOT/'.github/workflows/india.yml').read_text()
        for text in (daily,saturday):
            self.assertIn('group: india-dashboard-${{ github.ref }}',text)
            self.assertIn('cancel-in-progress: false',text)
            self.assertIn('queue: max',text)
            self.assertIn('ref: ${{ github.ref_name }}',text)
        self.assertIn('cron: "0 8 * * 6"',saturday)
        self.assertIn("cron: '10 15 * * *'",daily)
        self.assertIn('workflow_dispatch:',daily)
        self.assertIn('--refresh-recent --overlap 10',daily)
        self.assertIn('python -m charts.india_charts.india_monetary --refresh-current',daily)
        self.assertEqual(daily.count("if: steps.refresh.outputs.changed == 'true'"),2)
        for forbidden in ('generate_india.py','rbi_sentinel','india_macro.db','rbi_transmission',
                          'OPENAI','ANTHROPIC','claude','requirements.txt','git add -A'):
            self.assertNotIn(forbidden,daily)
        self.assertIn('git diff --cached --quiet',daily)
        self.assertIn('git add -- "$(python -m data.paths --relative RBI_MONEY_MARKET_CSV)"',daily)

    def test_cli_outputs_drive_noop_and_edition_publish_gates(self):
        import sys
        output = self.root/'github-output'
        with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), \
             patch.object(sys,'argv',['rbi_money_market','--refresh-recent','--overlap','10']), \
             patch.object(rbi,'refresh_recent',return_value=False) as refresh, \
             patch('builtins.print'):
            rbi.main()
        refresh.assert_called_once_with(rbi.DEFAULT_PATH,10)
        self.assertEqual(output.read_text(),'changed=false\n')
        with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), \
             patch.object(sys,'argv',['india_monetary','--refresh-current']), \
             patch.object(charts,'refresh_current',return_value=[self.edition/charts.WACR_SPREAD,
                                                                self.edition/charts.LIQUIDITY]), \
             patch('builtins.print'):
            charts.main()
        self.assertEqual(output.read_text(),'changed=false\nedition=2026-10\n')


if __name__ == '__main__':
    unittest.main()
