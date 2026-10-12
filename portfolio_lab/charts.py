"""Editorial research graphics: explicit scales, direct values, one question per view."""
from html import escape
import altair as alt
import numpy as np
import pandas as pd
from charts.style import EconStyle
from data.processors.portfolio_analytics import drawdown

COLORS = [EconStyle.LINE_BLUE, EconStyle.LINE_TEAL, EconStyle.TEXT_MUTED]
PALETTE = dict(zip(['Portfolio A','Portfolio B','Benchmark'], COLORS))


def _style(chart, inline=False):
    if inline:
        return (chart.properties(background='transparent', padding={'left':10,'right':38,'top':20,'bottom':18})
                .configure_view(stroke=None)
                .configure_axis(labelFont='Inter',titleFont='Inter',labelFontSize=13,titleFontSize=13,
                    labelColor='#343B45',titleColor='#343B45',titleFontWeight='normal',
                    domain=False,ticks=False,tickCount=5,labelPadding=10,titlePadding=16,
                    grid=False,labelOverlap=False)
                .configure_axisY(labelExpr="split(datum.label, '\\n')", labelLineHeight=16)
                .configure_axisX(grid=True,gridColor='#D6D8D2',gridOpacity=.65,gridWidth=.7)
                .configure_legend(labelFont='Inter',labelFontSize=13,labelColor='#343B45',
                    orient='top',title=None,direction='horizontal',symbolStrokeWidth=3,
                    labelLimit=240,padding=8,rowPadding=8,columnPadding=22)
                .configure_title(font='Inter',fontSize=18,anchor='start',color='#0A1F3D'))
    return (chart.properties(background='#FFFFFF', padding={'left':12,'right':22,'top':14,'bottom':14}).configure_view(stroke=None)
            .configure_axis(labelFont='Inter',titleFont='Inter',labelFontSize=12,titleFontSize=12,
                labelColor='#4B5563',titleColor='#4B5563',titleFontWeight='normal',
                domain=False,ticks=False,tickCount=5,labelPadding=9,titlePadding=12,gridColor='#E7E9EC',gridWidth=.6)
            .configure_legend(labelFont='Inter',labelFontSize=12,orient='top',title=None,
                direction='horizontal',symbolStrokeWidth=3,labelLimit=200)
            .configure_title(font='Inter',fontSize=16,anchor='start',color='#1A1A1A'))


def heading_html(title, subtitle):
    return ('<div class="pl-chart-heading"><h3>'+escape(title)+'</h3><p>'+escape(subtitle)+'</p></div>')


def format_inr(value):
    number=str(int(round(abs(value))));tail=number[-3:];head=number[:-3];groups=[]
    while head:groups.insert(0,head[-2:]);head=head[:-2]
    return ('−' if value<0 else '')+'₹'+','.join(groups+[tail])


def legend_html(results, values=True, is_drawdown=False, currency='USD'):
    entries=[]
    for name, result in results.items():
        end=drawdown(result.wealth).min()*100 if is_drawdown else result.wealth.iloc[-1]
        change=(result.wealth.iloc[-1]/result.wealth.iloc[0]-1)*100
        amount=format_inr(end) if currency=='INR' else '${:,.0f}'.format(end)
        number=('{:.1f}% max loss'.format(end) if is_drawdown else '{} ({:+.2f}%)'.format(amount,change)) if values else ''
        entries.append('<span><i style="background:{}"></i>{} <b>{}</b></span>'.format(PALETTE.get(name,COLORS[0]),escape(name),number))
    return '<div class="pl-chart-legend">'+''.join(entries)+'</div>'


def _data(frame):
    return alt.Data(values=frame.to_dict(orient='records'))


def _zero(axis='x'):
    return alt.Chart(alt.Data(values=[{'Zero':0}])).mark_rule(color='#59616B',strokeWidth=1.2).encode(**{axis:'Zero:Q'})


def paths(results, is_drawdown=False, log=False, height=440, currency='USD',observed_range=False,wealth_baseline=False):
    rows=[]; ends=[]
    for name, result in results.items():
        values=drawdown(result.wealth)*100 if is_drawdown else result.wealth
        rows.extend(dict(Date=d.isoformat(),Series=name,Value=float(v)) for d,v in values.items())
        ends.append(dict(Date=values.index[-1].isoformat(),Series=name,Value=float(values.iloc[-1])))
    names=list(results); palette=alt.Scale(domain=names,range=[PALETTE.get(n,COLORS[0]) for n in names])
    indian=currency=='INR' and not is_drawdown
    axis=alt.Axis(tickCount=6,format='.0f' if is_drawdown else '$~s',gridColor='#AAB2BC',gridOpacity=1,gridWidth=1)
    if indian:axis=alt.Axis(tickCount=5,gridColor='#AAB2BC',gridOpacity=1,gridWidth=1,labelExpr="datum.value >= 10000000 ? '₹'+format(datum.value/10000000,'.1f')+' cr' : '₹'+format(datum.value/100000,'.1f')+' lakh'")
    wealth_scale=None
    if wealth_baseline and not is_drawdown:
        initial=float(next(iter(results.values())).wealth.iloc[0])
        low=min(initial,min(r['Value'] for r in rows))
        high=max(initial,max(r['Value'] for r in rows))
        if log:
            wealth_scale=alt.Scale(type='log',domain=[low,high if high>low else low*1.01],zero=False,nice=False)
        else:
            span=max(high-low,initial*.01)
            magnitude=10**np.floor(np.log10(span/5))
            step=next(mult*magnitude for mult in [1,2,2.5,5,10] if mult*magnitude>=span/5)
            top=max(low+step,np.ceil(high/step)*step)
            ticks=sorted(set([initial]+list(np.arange(np.ceil(low/step)*step,top+step*.5,step))))
            axis=alt.Axis(**dict(axis.to_dict(),values=ticks))
            wealth_scale=alt.Scale(type='linear',domain=[low,top],zero=False,nice=False)
    y=alt.Y('Value:Q',title='Drawdown from episode peak (%)' if is_drawdown else 'Wealth · '+currency+(' · logarithmic scale' if log else ''),
        scale=wealth_scale if wealth_scale is not None else alt.Scale(type='log' if log and not is_drawdown else 'linear',zero=not log and not observed_range,nice=not log),
        axis=axis)
    x=alt.X('Date:T',title=None,axis=alt.Axis(format='%Y' if (next(iter(results.values())).wealth.index[-1]-next(iter(results.values())).wealth.index[0]).days>800 else '%b %Y',tickCount=5,grid=False,labelAngle=0))
    base=alt.Chart(alt.Data(values=rows)).encode(x=x,y=y,
        color=alt.Color('Series:N',scale=palette,legend=None),
        strokeDash=alt.StrokeDash('Series:N',scale=alt.Scale(domain=names,range=[[1,0] if n!='Benchmark' else [5,3] for n in names]),legend=None),
        tooltip=[alt.Tooltip('Date:T',format='%d %b %Y',title='Evaluation date'),'Series:N',alt.Tooltip('Value:Q',format=',.2f',title='Drawdown (%)' if is_drawdown else 'Wealth ('+('₹' if indian else '$')+')')])
    end=alt.Chart(alt.Data(values=ends)).mark_point(filled=True,size=75,stroke='white',strokeWidth=1.5).encode(x=x,y=y,color=alt.Color('Series:N',scale=palette,legend=None),tooltip=base.encoding.tooltip)
    reference=alt.Chart(alt.Data(values=[{'Value':0 if is_drawdown else next(iter(results.values())).wealth.iloc[0]}])).mark_rule(color='#9CA3AF',strokeDash=[3,4],strokeWidth=1).encode(y=y)
    chart=(reference+base.mark_line(strokeWidth=2.6,clip=True)+end).properties(height=height)
    return _style(chart)


def allocation_risk(table, portfolio='Portfolio A'):
    rows=(table*100).rename_axis('Asset').reset_index()
    rows['Label']=[f'{a}   {w:.1f}% capital' for a,w in zip(rows.Asset,rows.Allocation)]
    order=rows.sort_values('Risk contribution',ascending=False).Label.tolist()
    base=alt.Chart(_data(rows)).encode(y=alt.Y('Label:N',title=None,sort=order,axis=alt.Axis(labelLimit=230,labelExpr="split(datum.label, '   ')",labelLineHeight=16)),
         tooltip=['Asset:N',alt.Tooltip('Allocation:Q',format='.1f',title='Capital (%)'),alt.Tooltip('Risk contribution:Q',format='.1f',title='Variance contribution (%)')])
    x=alt.X('Risk contribution:Q',title='Share of portfolio variance (%)',scale=alt.Scale(zero=True,padding=45),axis=alt.Axis(tickCount=5))
    bars=base.mark_bar(size=20,color=PALETTE.get(portfolio,COLORS[0])).encode(x=x)
    weights=base.mark_point(shape='diamond',filled=True,size=95,opacity=1,color='#1A1A1A').encode(x=alt.X('Allocation:Q',title='Share of portfolio variance (%)'))
    positive=base.transform_filter('datum["Risk contribution"] >= 0').mark_text(align='left',dx=6,font='Inter',fontSize=13,fontWeight=600,color='#1A1A1A').encode(x=x,text=alt.Text('Risk contribution:Q',format='.1f'))
    negative=base.transform_filter('datum["Risk contribution"] < 0').mark_text(align='right',dx=-6,font='Inter',fontSize=13,fontWeight=600,color='#1A1A1A').encode(x=x,text=alt.Text('Risk contribution:Q',format='.1f'))
    labels=positive+negative
    return _style((_zero()+bars+weights+labels).properties(height=max(240,len(rows)*46)), inline=True)

def correlations(matrix):
    frame=matrix.rename_axis('Asset').reset_index().melt('Asset',var_name='Other asset',value_name='Correlation').dropna()
    base=alt.Chart(_data(frame)).encode(x=alt.X('Asset:N',title=None,axis=alt.Axis(labelAngle=0,orient='top')),y=alt.Y('Other asset:N',title=None),
         color=alt.Color('Correlation:Q',scale=alt.Scale(domain=[-1,0,1],range=[EconStyle.LINE_MAROON,'#F8F9FA',EconStyle.LINE_BLUE]),legend=alt.Legend(orient='bottom',direction='horizontal',gradientLength=180,title='Correlation',values=[-1,0,1])),
         tooltip=['Asset:N','Other asset:N',alt.Tooltip('Correlation:Q',format='.2f')])
    rect=base.mark_rect(stroke='#FFFFFF',strokeWidth=3)
    text=base.mark_text(font='Inter',fontSize=14,fontWeight=600).encode(text=alt.Text('Correlation:Q',format='.2f'),color=alt.condition('abs(datum.Correlation)>0.6',alt.value('white'),alt.value('#1A1A1A')))
    size=min(600,max(360,len(matrix)*52))
    return _style((rect if len(matrix)>10 else rect+text).properties(width=size,height=size))


def contribution_bars(frame):
    names=[n for n in ['Portfolio A','Portfolio B','Benchmark'] if n in frame]
    rows=frame.rename_axis('Holding').reset_index().melt('Holding',var_name='Portfolio',value_name='Contribution')
    rows=rows.loc[rows.Contribution.abs()>1e-12].copy(); rows['Contribution']*=100
    order=frame.abs().max(axis=1).sort_values(ascending=False).index.tolist()
    rows['Row']=rows.Holding if len(names)==1 else rows.Holding+' · '+rows.Portfolio.str.replace('Portfolio ','',regex=False)
    sort=[h if len(names)==1 else h+' · '+n.replace('Portfolio ','') for h in order for n in names if not rows.loc[(rows.Holding==h)&(rows.Portfolio==n)].empty]
    base=alt.Chart(_data(rows)).encode(y=alt.Y('Row:N',title=None,sort=sort,scale=alt.Scale(paddingInner=.55,paddingOuter=.25),axis=alt.Axis(labelOverlap=False,labelLimit=200)),
         x=alt.X('Contribution:Q',title='Realised contribution · percentage points',scale=alt.Scale(zero=True,padding=35),axis=alt.Axis(tickCount=5,format='~s')),
         color=alt.Color('Portfolio:N',scale=alt.Scale(domain=names,range=[PALETTE[n] for n in names]),legend=alt.Legend()),
         tooltip=['Holding:N','Portfolio:N',alt.Tooltip('Contribution:Q',format='+,.2f',title='Contribution (pp)')])
    positive=base.transform_filter('datum.Contribution >= 0').mark_text(font='Inter',fontSize=13,fontWeight=600,align='left',dx=6).encode(text=alt.Text('Contribution:Q',format='+,.2f'),color=alt.value('#1A1A1A'))
    negative=base.transform_filter('datum.Contribution < 0').mark_text(font='Inter',fontSize=13,fontWeight=600,align='right',dx=-6).encode(text=alt.Text('Contribution:Q',format='+,.2f'),color=alt.value('#1A1A1A'))
    labels=positive+negative
    return _style((_zero()+base.mark_bar(size=18)+labels).properties(height=max(240,len(rows)*64)), inline=True)

def research_lines(frame,ylabel,max_gap_days=None):
    rows=frame.rename_axis('Date').reset_index().melt('Date',var_name='Series',value_name='Value').dropna()
    rows['Segment']=rows.groupby('Series').Date.transform(lambda d:d.diff().dt.days.gt(max_gap_days).cumsum()) if max_gap_days else 0
    rows['Date']=rows.Date.map(lambda d:d.isoformat())
    chart=alt.Chart(_data(rows)).mark_line(strokeWidth=2.3,point=bool(max_gap_days)).encode(
        x=alt.X('Date:T',title=None,axis=alt.Axis(tickCount=5,grid=False,format='%Y')),
        y=alt.Y('Value:Q',title=ylabel,scale=alt.Scale(zero=False)),
        color=alt.Color('Series:N',scale=alt.Scale(range=COLORS),title=None),detail='Segment:N',
        tooltip=['Date:T','Series:N',alt.Tooltip('Value:Q',format='.3f')]).properties(height=300)
    return _style(chart)


def factor_intervals(model):
    # Coefficients are transformed into response to explicit economic shocks;
    # every row is now percentage points of portfolio return, including CI.
    shocks={'Equity':(-.10,'SPY −10%'),'Rate':(.01,'10Y yield +100 bp'),'Credit':(.01,'HY OAS +100 bp')}
    rows=[]
    for factor,(shock,label) in shocks.items():
        if factor not in model['table'].index:continue
        r=model['table'].loc[factor]; lo,hi=sorted([r['95% lower']*shock*100,r['95% upper']*shock*100])
        rows.append(dict(Factor=label,Response=r.Coefficient*shock*100,Low=lo,High=hi))
    base=alt.Chart(alt.Data(values=rows)).encode(y=alt.Y('Factor:N',title=None,sort=None,axis=alt.Axis(labelLimit=180)),
        x=alt.X('Response:Q',title='Estimated weekly return response (pp)',scale=alt.Scale(zero=True,padding=45),axis=alt.Axis(tickCount=5)),
        tooltip=['Factor:N',alt.Tooltip('Response:Q',format='+.2f'),alt.Tooltip('Low:Q',format='+.2f'),alt.Tooltip('High:Q',format='+.2f')])
    intervals=base.mark_rule(color=EconStyle.LINE_BLUE,strokeWidth=3).encode(x=alt.X('Low:Q',axis=alt.Axis(tickCount=5)),x2='High:Q')
    points=base.mark_point(filled=True,size=100,opacity=1,color=EconStyle.LINE_BLUE)
    caps = base.mark_tick(color=EconStyle.LINE_BLUE, thickness=2, size=12).encode(x='Low:Q') + base.mark_tick(color=EconStyle.LINE_BLUE, thickness=2, size=12).encode(x='High:Q')
    values = base.mark_text(font='Inter', fontSize=13, fontWeight=600, align='left', dx=12, color='#1A1A1A').encode(x='High:Q', text=alt.Text('Response:Q', format='+.2f'))
    return _style((_zero()+intervals+caps+points+values).properties(height=200), inline=True)

def regime_distribution(observations,names):
    rows=[]
    for regime,group in observations.groupby('Regime'):
        for name in names:
            v=group[name].dropna()*100; q=v.quantile([.1,.25,.5,.75,.9])
            rows.append(dict(Group=regime+' · '+name.replace('Portfolio ','')+' · n='+str(len(v)),Portfolio=name,
                             P10=q.loc[.1],P25=q.loc[.25],Median=q.loc[.5],P75=q.loc[.75],P90=q.loc[.9]))
    base=alt.Chart(alt.Data(values=rows)).encode(y=alt.Y('Group:N',title=None,sort=None,axis=alt.Axis(labelLimit=220,labelOverlap=False)),
          color=alt.Color('Portfolio:N',scale=alt.Scale(domain=names,range=[PALETTE[n] for n in names]),title=None,legend=alt.Legend(columns=1,direction='vertical')),
          tooltip=['Group:N',alt.Tooltip('P10:Q',format='.2f'),alt.Tooltip('Median:Q',format='.2f'),alt.Tooltip('P90:Q',format='.2f')])
    outer=base.mark_rule(strokeWidth=2).encode(x=alt.X('P10:Q',title='Monthly return (%)',scale=alt.Scale(zero=True,padding=45),axis=alt.Axis(tickCount=5)),x2='P90:Q')
    inner=base.mark_rule(strokeWidth=10,opacity=.45).encode(x='P25:Q',x2='P75:Q')
    median=base.mark_point(filled=True,size=75,opacity=1).encode(x='Median:Q')
    values = base.mark_text(font='Inter', fontSize=13, fontWeight=600, align='left', dx=10, color='#1A1A1A').encode(x='P90:Q', text=alt.Text('Median:Q', format='+.1f'))
    return _style((_zero()+outer+inner+median+values).properties(height=max(320,len(rows)*64+len(names)*22)), inline=True)

def regime_strip(observations):
    # One categorical band puts the time axis below the strip. Merge only
    # adjacent months of the same state; missing months stay visible gaps.
    segments=[]
    for month, regime in observations['Regime'].sort_index().items():
        start=month.to_timestamp().isoformat()
        end=(month+1).to_timestamp().isoformat()
        if segments and segments[-1]['Regime']==regime and segments[-1]['End']==start:
            segments[-1]['End']=end
        else:
            segments.append(dict(Date=start, End=end, Regime=regime, Timeline='History'))
    states=list(dict.fromkeys(observations['Regime']))
    colors={'Falling':EconStyle.LINE_MAROON,'Rising':EconStyle.LINE_TEAL,
            'Unchanged':EconStyle.TEXT_MUTED,'Below trend':EconStyle.LINE_MAROON,
            'At/above trend':EconStyle.LINE_TEAL,'Tightening':EconStyle.LINE_MAROON,
            'Easing':EconStyle.LINE_TEAL,'INR depreciation':EconStyle.LINE_MAROON,
            'INR appreciation':EconStyle.LINE_TEAL}
    chart=alt.Chart(alt.Data(values=segments)).mark_rect(height=24).encode(
        x=alt.X('Date:T',title=None,axis=alt.Axis(orient='bottom',grid=False,tickCount=5,format='%Y',labelPadding=10),scale=alt.Scale(nice=False)),
        x2='End:T',y=alt.Y('Timeline:N',axis=None,scale=alt.Scale(paddingInner=0,paddingOuter=0)),
        color=alt.Color('Regime:N',scale=alt.Scale(domain=states,range=[colors.get(s,COLORS[i % len(COLORS)]) for i,s in enumerate(states)]),title=None,
                        legend=alt.Legend(orient='top',direction='horizontal',offset=10)),
        tooltip=[alt.Tooltip('Date:T',title='From',format='%b %Y'),alt.Tooltip('End:T',title='Until (exclusive)',format='%b %Y'),'Regime:N'],
    ).properties(height=115)
    return _style(chart,inline=True).properties(padding={'left':10,'right':38,'top':0,'bottom':4})


def stress_risk_change(before,during,portfolio,height=None):
    rows=pd.DataFrame({'Before':before['table']['Risk contribution']*100,'During':during['table']['Risk contribution']*100}).rename_axis('Asset').reset_index()
    rows['Change']=rows.During-rows.Before
    rows['LabelX']=rows[['Before','During']].max(axis=1)
    order=rows.sort_values('During',ascending=False).Asset.tolist()
    base=alt.Chart(_data(rows)).encode(y=alt.Y('Asset:N',title=None,sort=order),
         tooltip=['Asset:N',alt.Tooltip('Before:Q',format='.1f',title='Pre-stress (%)'),alt.Tooltip('During:Q',format='.1f',title='During stress (%)'),alt.Tooltip('Change:Q',format='+.1f',title='Change (pp)')])
    line=base.mark_rule(color='#A9B1B9',strokeWidth=2).encode(x=alt.X('Before:Q',title='Share of portfolio variance (%)',scale=alt.Scale(zero=True,padding=25)),x2='During:Q')
    pre=base.mark_point(shape='diamond',filled=True,size=90,opacity=1,color='#1A1A1A').encode(x='Before:Q')
    stress=base.mark_point(filled=True,size=110,opacity=1,color=PALETTE[portfolio]).encode(x='During:Q')
    values=base.mark_text(font='Inter',fontSize=13,fontWeight=600,align='left',dx=10,color='#1A1A1A').encode(x='LabelX:Q',text=alt.Text('During:Q',format='.1f'))
    return _style((_zero()+line+pre+stress+values).properties(height=height or max(220,len(rows)*44)), inline=True)
