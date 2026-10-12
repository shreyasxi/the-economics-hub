"""Prepared INR inputs; no remote work on interaction."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class IndiaUITests(unittest.TestCase):
    def test_mode_templates_sip_research_and_global_state(self):
        from data.fetchers.portfolio_india import current
        try:current()
        except OSError:self.skipTest('INR snapshot unavailable')
        with patch('data.fetchers.portfolio_india.collect',side_effect=AssertionError('Remote UI fetch')):
            app=AppTest.from_string('from portfolio_lab.page import render\nrender()',default_timeout=40).run()
            app.button(key='pl_enter_global').click().run()
            app.number_input(key='pl_a_SPY').set_value(70).run()
            app.number_input(key='pl_a_AGG').set_value(30).run()
            app.radio(key='pl_mode').set_value('Indian Investor — INR').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertEqual(app.number_input(key='in_a_NIFTYBEES.NS').value,60)
            app.checkbox(key='in_compare').check().run()
            app.selectbox(key='in_b_template').set_value('India and international').run()
            self.assertEqual(app.number_input(key='in_b_SPY').value,20)
            for view in ['Overview','Performance Attribution','Risk','Macro Regimes','Stress Testing']:
                app.radio(key='in_view').set_value(view).run()
                self.assertFalse(app.exception,[e.message for e in app.exception])
                self.assertEqual(app.number_input(key='in_b_SPY').value,20)
            self.assertNotIn('Risk & factors',app.radio(key='in_view').options)
            self.assertTrue(any('Sortino ratio</th>' in m.value for m in app.markdown))
            self.assertIn('(NIFTYBEES)', app.number_input(key='in_a_NIFTYBEES.NS').label)
            self.assertTrue(any('unavailable' in w.value.lower() for w in app.warning))
            app.selectbox(key='in_episode').set_value('RBI tightening 2022–23').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            app.selectbox(key='in_stress_mode').set_value('Direct asset and FX shocks').run()
            self.assertTrue(app.number_input(key='in_fx_shock'))
            app.radio(key='in_investment').set_value('Monthly SIP').run()
            self.assertFalse(app.exception,[e.message for e in app.exception])
            self.assertTrue(any('SIP | Invested Capital' in m.value for m in app.markdown))
            app.radio(key='pl_mode').set_value('Global Portfolio — USD').run()
            self.assertEqual(app.number_input(key='pl_a_SPY').value,70)
            self.assertEqual(app.number_input(key='pl_a_AGG').value,30)
            app.radio(key='pl_mode').set_value('Indian Investor — INR').run()
            self.assertEqual(app.number_input(key='in_b_SPY').value,20)
            self.assertFalse(app.exception,[e.message for e in app.exception])
