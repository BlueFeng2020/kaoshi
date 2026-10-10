"""Local PNG output; no browser network assets and no interactive backend."""
import os
from pathlib import Path
from config import RESOURCE_ROOT


def generate_charts(data, root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    cache=root.parent/'matplotlib-cache'; cache.mkdir(exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    os.environ.setdefault('XDG_CACHE_HOME',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import font_manager, rcParams
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    font_path=RESOURCE_ROOT/'static/fonts/NotoSansCJK-Regular.ttc'
    font_manager.fontManager.addfont(str(font_path))
    rcParams['font.family']=font_manager.FontProperties(fname=str(font_path)).get_name()
    rcParams['axes.unicode_minus']=False
    rcParams['font.size']=10
    result={}

    def save(key,title,draw):
        fig=Figure(figsize=(11,4.8),layout='constrained'); FigureCanvasAgg(fig)
        ax=fig.subplots(); draw(ax)
        ax.set_title(f'{title}  |  抽签序号：{data.exam_id}',pad=16)
        ax.spines[['top','right']].set_visible(False)
        ax.grid(axis='y',alpha=.18)
        filename=f'{key}_{data.exam_id}.png'
        fig.savefig(root/filename,dpi=130,facecolor='white')
        result[key]=filename

    def category(ax):
        import numpy as np
        p=data.category.pivot(index='设备类别',columns='设备状态',values='平均使用周期年')
        x=np.arange(len(p)); n=max(len(p.columns),1); width=.8/n
        for i,col in enumerate(p.columns):
            ax.bar(x-.4+width/2+i*width,p[col],width,label=col)
        ax.set_xticks(x,p.index,rotation=35,ha='right');ax.set_ylabel('平均年数');ax.legend()
    save('category','类别平均实际使用周期',category)
    save('status','完整生命周期与已运行时长',lambda ax:(ax.bar(data.status['设备状态'].map({'在用':'在用：已运行时长','已报废':'已报废：完整生命周期'}).fillna(data.status['设备状态']),data.status['平均使用周期年'],color=['#147d92','#e99a35'][:len(data.status)]),ax.set_ylabel('平均年数')))
    def scatter(ax):
        for status,g in data.correlation_data.groupby('设备状态'):
            ax.scatter(g['使用周期(年)'],g['有效累计维修单数'],s=18,alpha=.45,label=status)
        ax.set_xlabel('使用周期（年；在用为截至 2026-09-22 已运行时长）');ax.set_ylabel('全量有效累计维修单数');ax.legend()
    save('correlation','周期与故障频次（全量有效维修）',scatter)
    def bar(ax,frame,x,y,ylabel):
        ax.bar(frame[x],frame[y],color='#147d92');ax.tick_params(axis='x',labelrotation=30);ax.set_ylabel(ylabel)
    save('faults','故障类型分布（原始全量，含异常）',lambda ax:bar(ax,data.faults,'故障类型','原始维修次数','维修次数'))
    def monthly(ax):
        t=data.monthly; x=list(range(len(t)))
        ax.plot(x,t['停机小时合计'],color='#147d92',linewidth=1.5)
        step=max(1,len(t)//12); ticks=x[::step]
        ax.set_xticks(ticks,t['月份'].iloc[::step],rotation=40,ha='right');ax.set_ylabel('有效停机小时合计')
    save('monthly','按报修月份汇总停机时长（全量有效维修）',monthly)
    save('workshop_count','车间维保频次（全量有效维修）',lambda ax:bar(ax,data.workshops,'所属车间','有效维修单数','有效维修单数'))
    save('workshop_cost','车间维修费用（排除缺失及负费用）',lambda ax:bar(ax,data.workshops,'所属车间','维修费用合计元','维修费用（元）'))
    return result
