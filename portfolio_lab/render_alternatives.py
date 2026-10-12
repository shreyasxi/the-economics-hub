"""Reproducible local composition trials, using actual prepared prices."""
from pathlib import Path
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
from charts.style import EconStyle
from data.fetchers.portfolio_prices import load_bundle,snapshot_path
from data.processors.portfolio_analytics import compare,drawdown,metrics
from data.processors.portfolio_stress import diversification_windows
from config.portfolio_settings import TEMPLATES
from portfolio_lab.charts import PALETTE

OUT=Path('output/portfolio_lab/redesign/alternatives')


def axes_style(ax):
    for edge in ['top','right','left']:ax.spines[edge].set_visible(False)
    ax.grid(axis='y',color='#E7E9EC',linewidth=.5)
    ax.grid(axis='x',visible=False);ax.set_axisbelow(True)
    ax.tick_params(length=0,pad=8,labelsize=10)


def finish(fig,title,subtitle,name):
    EconStyle.add_editorial_header(fig,title,subtitle)
    EconStyle.add_source(fig,'Coin Metrics; Yahoo Finance · local research', '11 Oct 2026')
    EconStyle.save_chart(fig,OUT/name)
    plt.close(fig)


def wealth_trials(results):
    fig,ax=EconStyle.create_figure(size=(12,7))
    fig.subplots_adjust(left=.08,right=.95,bottom=.15,top=.72)
    for name,r in results.items():
        ax.plot(r.wealth.index,r.wealth,color=PALETTE[name],lw=2.2,ls='--' if name=='Benchmark' else '-',label=f'{name}   ${r.wealth.iloc[-1]:,.0f}')
        ax.scatter(r.wealth.index[-1],r.wealth.iloc[-1],color=PALETTE[name],s=36,edgecolors='white',zorder=5)
    ax.axhline(10000,color='#9CA3AF',lw=.8,ls=':');ax.set_ylabel('Wealth · USD')
    ax.yaxis.set_major_formatter(mticker.StrMethodFormatter('${x:,.0f}'))
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.03),ncol=3,frameon=False,fontsize=10)
    axes_style(ax);ax.xaxis.set_major_locator(mdates.YearLocator(2));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    finish(fig,'Growth of $10,000 | One shared wealth path','Alternative 1 · a common dollar scale, final values above, substantial plotting area','wealth-1-overlay.png')
    fig,axs=EconStyle.create_figure(size=(12,7),nrows=2,gridspec_kw={'height_ratios':[2,1]},sharex=True)
    fig.subplots_adjust(left=.08,right=.95,bottom=.15,top=.76,hspace=.15)
    for name,r in results.items():
        axs[0].plot(r.wealth.index,r.wealth,color=PALETTE[name],lw=2,label=name)
        axs[1].plot(r.wealth.index,drawdown(r.wealth)*100,color=PALETTE[name],lw=1.5)
    axs[0].legend(loc='upper left',ncol=3,frameon=False);axs[0].set_ylabel('Wealth · USD')
    axs[0].yaxis.set_major_formatter(mticker.StrMethodFormatter('${x:,.0f}'))
    axs[1].set_ylabel('Drawdown (%)');axs[1].axhline(0,color='#9CA3AF',lw=.7)
    for ax in axs:axes_style(ax)
    axs[1].xaxis.set_major_locator(mdates.YearLocator(2));axs[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    finish(fig,'Growth and the cost of staying invested','Alternative 2 · aligned wealth and drawdown panels; two separate, clearly labelled scales','wealth-2-wealth-drawdown.png')


def stress_trials(study,chosen):
    before=study['estimates']['Pre-stress'][chosen];during=study['estimates']['During stress (ex-post)'][chosen]
    for version in [1,2]:
        fig,axs=EconStyle.create_figure(size=(12,7),ncols=2,gridspec_kw={'width_ratios':[1.1,1]})
        fig.subplots_adjust(left=.08,right=.94,bottom=.16,top=.70,wspace=.35)
        for name,r in study['results'].items():
            if name=='Benchmark':continue
            axs[0].plot(r.wealth.index,drawdown(r.wealth)*100,lw=2.2,color=PALETTE[name],label=name)
        axs[0].set_title('What happened to the portfolios?',loc='left',fontsize=12,weight='bold',pad=48)
        axs[0].set_ylabel('Drawdown from episode peak (%)');axs[0].legend(frameon=False,loc='lower left');axes_style(axs[0])
        axs[0].xaxis.set_major_locator(mdates.MonthLocator(interval=3));axs[0].xaxis.set_major_formatter(mdates.DateFormatter('%b\n%Y'))
        if version==1:
            b=before['table']['Risk contribution']*100;d=during['table']['Risk contribution']*100
            order=d.sort_values().index;labels=order.tolist();v1=b.loc[order];v2=d.loc[order]
            title='Where did risk concentrate?';xlabel='Share of variance (%)'
        else:
            cb=before['correlation'];cd=during['correlation'];pairs=[(x,y) for i,x in enumerate(cb) for y in list(cb)[i+1:]]
            pairs=sorted(pairs,key=lambda xy:abs(cd.loc[xy]-cb.loc[xy]),reverse=True)[:6]
            labels=[x+' / '+y for x,y in pairs];v1=np.array([cb.loc[xy] for xy in pairs]);v2=np.array([cd.loc[xy] for xy in pairs])
            title='Which relationships shifted most?';xlabel='Pairwise correlation · largest absolute changes'
        y=np.arange(len(labels));axs[1].hlines(y,v1,v2,color='#A9B1B9',lw=2)
        axs[1].scatter(v1,y,color='#1A1A1A',marker='D',s=40,label='Before')
        axs[1].scatter(v2,y,color=PALETTE[chosen],s=60,label='During (ex-post)')
        axs[1].set_yticks(y);axs[1].set_yticklabels(labels);axs[1].axvline(0,color='#9CA3AF',lw=.7)
        axs[1].set_title(title,loc='left',fontsize=12,weight='bold',pad=48)
        axs[1].set_xlabel(xlabel,fontsize=9);axs[1].legend(loc='lower left',bbox_to_anchor=(0,1.03),ncol=2,frameon=False,fontsize=9)
        if version==2:axs[1].set_xlim(-1,1)
        axes_style(axs[1]);axs[1].grid(axis='y',visible=False);axs[1].grid(axis='x',visible=True,color='#E7E9EC',linewidth=.5)
        fig.text(.08,.08,'Same target weights · pre-stress n={} · during n={} · ex-post covariance; no forecast'.format(before['observations'],during['observations']),fontsize=9,color='#4B5563')
        finish(fig,'Diversification Under Stress | The 2022 sell-off','Alternative '+str(version)+' · losses paired with '+('before/during risk concentration' if version==1 else 'before/during correlation shifts'),f'stress-{version}.png')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    prices,manifest=load_bundle(snapshot_path());a=TEMPLATES['Traditional 60/40'];b=TEMPLATES['Bitcoin & oil research']
    common,results=compare(prices,a,b,start='2014-01-01',rebalancing='Monthly',cost_bps=5)
    wealth_trials(results)
    study=diversification_windows(prices,a,b,'SPY','2022 Equity and Bond Sell-Off','Monthly',5)
    stress_trials(study,'Portfolio B')
    (OUT/'results.json').write_text(json.dumps(dict(snapshot=snapshot_path().name,start=str(common.index[0].date()),end=str(common.index[-1].date()),outcomes={n:metrics(r) for n,r in results.items()}),indent=2))

if __name__=='__main__':main()
