"""Six reproducible composition trials, using actual validated INR histories."""
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from matplotlib.colors import LinearSegmentedColormap
from charts.style import EconStyle
from portfolio_lab.verify_india import main,A,B
from data.processors.portfolio_analytics import drawdown
from data.processors.portfolio_sip import sip
from portfolio_lab.charts import PALETTE,format_inr

OUT=Path('output/portfolio_lab/india/alternatives');OUT.mkdir(parents=True,exist_ok=True)


def style(ax,inr=False):
    for edge in ['top','right','left']:ax.spines[edge].set_visible(False)
    ax.grid(axis='y',color='#AAB2BC',linewidth=.6);ax.set_axisbelow(True);ax.tick_params(length=0,pad=8,labelsize=10)
    ax.grid(axis='x',visible=False);ax.margins(x=.01)
    if inr:ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:'₹{:.1f} lakh'.format(x/100000)))


def finish(fig,title,subtitle,name):
    EconStyle.add_editorial_header(fig,title,subtitle)
    EconStyle.add_source(fig,'NSE TRI; Yahoo ETF prices; Federal Reserve H.10 · portfolio research','12 Oct 2026')
    EconStyle.save_chart(fig,OUT/name);plt.close(fig)


def render():
    prices,results,sip_b,study=main()
    fig,ax=EconStyle.create_figure(size=(12,7));fig.subplots_adjust(left=.11,right=.96,bottom=.15,top=.72)
    for name,r in results.items():
        ax.plot(r.wealth.index,r.wealth,color=PALETTE[name],lw=2.5,ls='--' if name=='Benchmark' else '-',label=name+' '+format_inr(r.wealth.iloc[-1]))
        ax.scatter(r.wealth.index[-1],r.wealth.iloc[-1],s=36,color=PALETTE[name],zorder=5)
    ax.axhline(100000,color='#87919C',ls=':',lw=1);ax.legend(loc='lower left',bbox_to_anchor=(0,1.03),ncol=3,frameon=False,fontsize=10)
    ax.set_ylabel('Wealth · INR');style(ax,True);ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    finish(fig,'Growth of ₹1,00,000 | A shared wealth comparison','Option 1 · observed wealth range (nonzero axis) · October 2021–October 2026 · weekly reference marks','wealth-1.png')
    fig,axs=EconStyle.create_figure(size=(12,7),nrows=2,sharex=True,gridspec_kw={'height_ratios':[2,1]});fig.subplots_adjust(left=.11,right=.96,bottom=.15,top=.75,hspace=.14)
    for name,r in results.items():
        axs[0].plot(r.wealth.index,r.wealth,color=PALETTE[name],lw=2.2,label=name)
        axs[1].plot(r.wealth.index,drawdown(r.wealth)*100,color=PALETTE[name],lw=1.8)
    axs[0].legend(ncol=3,frameon=False);axs[0].set_ylabel('Wealth · INR');axs[1].set_ylabel('Drawdown (%)');style(axs[0],True);style(axs[1]);axs[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    finish(fig,'Wealth accumulation and the cost of staying invested','Option 2 · aligned wealth and drawdown; separate labelled panels, one time axis','wealth-2.png')
    sip_a=sip(prices,A,'2021-10-01',prices.index[-1],10000,0,1,'Monthly',5)
    flows={'Portfolio A':sip_a,'Portfolio B':sip_b}
    fig,ax=EconStyle.create_figure(size=(12,7));fig.subplots_adjust(left=.11,right=.96,bottom=.15,top=.72)
    for name,r in flows.items():ax.plot(r['wealth'].index,r['wealth'],color=PALETTE[name],lw=2.5,label=name+' '+format_inr(r['wealth'].iloc[-1]))
    ax.step(sip_b['invested'].index,sip_b['invested'],where='post',color='#1A1A1A',ls='--',lw=2,label='Capital '+format_inr(sip_b['invested'].iloc[-1]))
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.03),ncol=3,frameon=False,fontsize=10);style(ax,True);ax.set_ylabel('INR · portfolio value and capital');ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    finish(fig,'SIP | Invested capital versus portfolio value','Option 1 · same ₹10,000 monthly contributions, same reference dates · capital is not investment profit','sip-1.png')
    fig,axs=EconStyle.create_figure(size=(12,7),ncols=2,sharey=True);fig.subplots_adjust(left=.11,right=.96,bottom=.15,top=.74,wspace=.15)
    for ax,(name,r) in zip(axs,flows.items()):
        ax.plot(r['wealth'].index,r['wealth'],color=PALETTE[name],lw=2.2,label='Portfolio value')
        ax.step(r['invested'].index,r['invested'],where='post',color='#1A1A1A',ls='--',lw=1.5,label='Invested capital')
        ax.fill_between(r['wealth'].index,r['invested'],r['wealth'],color=PALETTE[name],alpha=.15)
        ax.set_title(name+' · gain '+format_inr(r['gain'].iloc[-1]),loc='left',fontsize=12,pad=20)
        style(ax,True);ax.xaxis.set_major_locator(mdates.YearLocator(2));ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    axs[0].legend(loc='upper left',frameon=False,fontsize=9);axs[0].set_ylabel('INR · shared scale')
    finish(fig,'SIP | Two capital journeys on one rupee scale','Option 2 · portfolio small multiples; shaded difference reveals investment gain or loss','sip-2.png')
    before=study['estimates']['Pre-stress']['Portfolio B'];during=study['estimates']['During stress (ex-post)']['Portfolio B']
    fig,axs=EconStyle.create_figure(size=(12,7),ncols=2,gridspec_kw={'width_ratios':[1.1,1]});fig.subplots_adjust(left=.08,right=.96,bottom=.17,top=.72,wspace=.3)
    for name,r in study['results'].items():axs[0].plot(r.wealth.index,drawdown(r.wealth)*100,color=PALETTE[name],lw=2,label=name,ls='--' if name=='Benchmark' else '-')
    axs[0].set_title('What happened to portfolio losses?',loc='left',fontsize=13,pad=40);axs[0].legend(loc='lower left',frameon=False,fontsize=9);axs[0].set_ylabel('Drawdown from episode peak (%)');style(axs[0])
    labels={'NIFTYBEES.NS':'Nifty 50 ETF','GILT5YBEES.NS':'5yr G-Sec ETF','GOLDBEES.NS':'Gold ETF'}
    table=before['table'].join(during['table'][['Risk contribution']],rsuffix=' during')*100
    for i,(asset,row) in enumerate(table.iterrows()):
        axs[1].plot([row['Risk contribution'],row['Risk contribution during']],[i,i],color='#AAB2BC',lw=2)
        axs[1].scatter(row['Risk contribution'],i,marker='D',color='#1A1A1A',s=45,label='Before' if i==0 else None)
        axs[1].scatter(row['Risk contribution during'],i,color=PALETTE['Portfolio B'],s=50,label='During · ex-post' if i==0 else None)
    axs[1].set_yticks(range(len(table)));axs[1].set_yticklabels([labels[k] for k in table.index]);axs[1].invert_yaxis();axs[1].axvline(0,color='#87919C',lw=1)
    axs[1].set_title('Portfolio B | Where did risk concentrate?',loc='left',fontsize=13,pad=40);axs[1].legend(loc='lower left',bbox_to_anchor=(0,1),ncol=2,frameon=False,fontsize=9)
    style(axs[1]);axs[1].grid(axis='y',visible=False);axs[1].grid(axis='x',color='#E7E9EC',linewidth=.5);axs[1].set_xlabel('Share of variance (%)')
    axs[0].xaxis.set_major_locator(mdates.MonthLocator(interval=3));axs[0].xaxis.set_major_formatter(mdates.DateFormatter('%b\n%Y'))
    fig.text(.08,.095,'52 weekly pre-stress returns; 41 during · same target weights · ex-post covariance; no causal claim',fontsize=10,color='#4B5563')
    finish(fig,'India Diversification Under Stress | RBI tightening 2022–23','Option 1 · losses paired with before/during risk contributions · May 2022–February 2023','stress-1.png')
    fig=plt.figure(figsize=(12,8));grid=fig.add_gridspec(2,2,height_ratios=[1.2,1]);fig.subplots_adjust(left=.08,right=.96,bottom=.14,top=.78,hspace=.55,wspace=.3)
    top=fig.add_subplot(grid[0,:])
    for name,r in study['results'].items():top.plot(r.wealth.index,drawdown(r.wealth)*100,color=PALETTE[name],lw=2,label=name)
    top.legend(ncol=3,frameon=False,fontsize=10);top.set_ylabel('Drawdown (%)');style(top);top.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    cmap=LinearSegmentedColormap.from_list('Monetaria',['#9B1C31','#FFFFFF','#245A94'])
    for slot,estimate,title in [(grid[1,0],before,'Before · 52 weekly returns'),(grid[1,1],during,'During · 41 returns · ex-post')]:
        ax=fig.add_subplot(slot);matrix=estimate['correlation'];ax.imshow(matrix,vmin=-1,vmax=1,cmap=cmap,aspect='auto')
        names=[labels[k] for k in matrix];ax.set_xticks(range(len(names)));ax.set_xticklabels(names,fontsize=9);ax.set_yticks(range(len(names)));ax.set_yticklabels(names,fontsize=9);ax.set_title(title,loc='left',fontsize=12,pad=12)
        for i in range(len(names)):
            for j in range(len(names)):ax.text(j,i,f'{matrix.iloc[i,j]:.2f}',ha='center',va='center',color='white' if abs(matrix.iloc[i,j])>.6 else '#1A1A1A',fontsize=11)
    finish(fig,'India Diversification Under Stress | Relationships shifted','Option 2 · full-width losses above before/during correlation matrices · colour scale fixed −1 to +1','stress-2.png')
    print('Six real-data composition previews saved:',OUT,flush=True)


if __name__=='__main__':render()
