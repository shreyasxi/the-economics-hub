"""Official NSE schema, observed dates and five separate source checks."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
import pytest
import data.fetchers.nse_tri as tri
from config.market_matrix import OFFICIAL_TOTAL_RETURN

FIXTURE=Path(__file__).parent/'fixtures/nse_tri/recent_records.json'


def test_live_captured_official_schema():
    raw=json.loads(FIXTURE.read_text())
    result=tri.parse_response(raw,'2026-09-25','2026-10-01')
    assert result.attrs['return_method']==OFFICIAL_TOTAL_RETURN
    assert result.index.is_monotonic_increasing
    assert result.loc['2026-10-01']==34070.01
    assert result.loc['2026-09-30']==34371.66
    assert result.loc['2026-09-29']==34517.11
    assert result.loc['2026-09-28']==34614.46
    assert result.loc['2026-09-25']==35161.85
    assert len(result)==5
    assert pd.Timestamp('2026-09-26') not in result.index
    assert tri.parse_response({'d':json.dumps(raw)},'2026-09-25','2026-10-01').equals(result)


@pytest.mark.parametrize('changes,message',[
    ({'Index Name':'Nifty Next 50'},'different index'),
    ({'TotalReturnsIndex':'nan'},'positive and finite'),
    ({'TotalReturnsIndex':'inf'},'positive and finite'),
    ({'TotalReturnsIndex':'0'},'positive and finite'),
    ({'Date':'02 Oct 2026'},'outside requested'),
])
def test_reject_invalid_official_record(changes,message):
    row=dict(json.loads(FIXTURE.read_text())[0],**changes)
    with pytest.raises(ValueError,match=message):tri.parse_response([row],'2026-09-25','2026-10-01')


def test_no_price_or_net_return_fallback_and_duplicate_rejection():
    row=json.loads(FIXTURE.read_text())[0]
    price=dict(row);price.pop('TotalReturnsIndex');price['Close']=25000
    with pytest.raises(ValueError,match='gross TotalReturnsIndex'):tri.parse_response([price],'2026-09-25','2026-10-01')
    with pytest.raises(ValueError,match='duplicate'):tri.parse_response([row,row],'2026-09-25','2026-10-01')
    with pytest.raises(ValueError,match='record array'):tri.parse_response({'data':[row]},'2026-09-25','2026-10-01')


class OfficialClient:
    """Synthetic official-schema transport: exact dates and deterministic levels."""
    def __init__(self,wrong_check=False,empty_year=False):self.calls=[];self.wrong_check=wrong_check;self.empty_year=empty_year
    def post(self,url,json,timeout):
        info=__import__('json').loads(json['cinfo']);self.calls.append((url,info))
        start=pd.Timestamp(info['startDate']);end=pd.Timestamp(info['endDate'])
        level=1000+(start-pd.Timestamp('2020-01-01')).days
        if self.wrong_check and start==end:level+=1
        raw=[{'Index Name':'Nifty 50','Date':start.strftime('%d %b %Y'),'TotalReturnsIndex':str(level),'NTR_Value':'1'}]
        if self.empty_year and len(self.calls)==2:raw=[]
        response=Mock();response.json.return_value=raw
        return response


def test_annual_windows_and_five_separate_historical_rechecks(monkeypatch,tmp_path):
    monkeypatch.setattr(tri,'HISTORY_START','2020-01-01')
    client=OfficialClient();fetch=tri.NiftyTRIFetcher(client=client,audit_dir=tmp_path)
    result=fetch.get_nifty50_tri('2026-10-03')
    assert len(result)==7
    assert len(result.attrs['source_checks'])==5
    assert all(c['value']==c['verified_value'] for c in result.attrs['source_checks'])
    for url,info in client.calls:
        assert url==tri.ENDPOINT and info['indexName']=='NIFTY 50'
        assert 0<=(pd.Timestamp(info['endDate'])-pd.Timestamp(info['startDate'])).days<=365
    assert len([r for r in fetch.requests if r['role']=='validation'])==5
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    assert manifest['observations']==7 and len(manifest['source_checks'])==5


def test_failed_recheck_and_missing_history_abort(monkeypatch):
    monkeypatch.setattr(tri,'HISTORY_START','2020-01-01')
    with pytest.raises(ValueError,match='historical-date check'):tri.NiftyTRIFetcher(OfficialClient(wrong_check=True)).get_nifty50_tri('2026-10-03')
    with pytest.raises(ValueError,match='empty historical window'):tri.NiftyTRIFetcher(OfficialClient(empty_year=True)).get_nifty50_tri('2026-10-03')
    with pytest.raises(ValueError,match='365'):tri.NiftyTRIFetcher(OfficialClient())._window('2020-01-01','2022-01-01')


def test_transport_failure_never_reads_old_values(monkeypatch):
    monkeypatch.setattr(tri.time,'sleep',lambda _:None)
    client=Mock();client.post.side_effect=RuntimeError('network blocked')
    with pytest.raises(ValueError,match='Official NSE TRI retrieval failed'):tri.NiftyTRIFetcher(client)._window('2020-01-01','2020-01-02')
    assert client.post.call_count==2


def test_five_live_historical_values_match_separate_nse_requests():
    root=FIXTURE.parent
    records=json.loads((root/'historical_records.json').read_text())
    series=tri.parse_response(records,'1990-07-03','2026-10-03')
    expected={'1999-06-30':1256.38,'2006-03-29':3971.57,'2013-01-22':7776.72,
              '2019-12-05':16865.04,'2026-10-01':34070.01}
    checks=json.loads((root/'historical_checks.json').read_text())
    assert len(checks)==5
    for point in checks:
        assert series.loc[point['date']]==point['value']==point['verified_value']==expected[point['date']]
        assert point['source_url']==tri.ENDPOINT
