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
    save('faults','故障类型分布（清洗后有效记录，含未分类）',lambda ax:bar(ax,data.faults,'故障类型','有效维修次数','有效维修次数'))
    def monthly(ax):
        t=data.monthly; x=list(range(len(t)))
        ax.plot(x,t['停机小时合计'],color='#147d92',linewidth=1.5)
        step=max(1,len(t)//12); ticks=x[::step]
        ax.set_xticks(ticks,t['月份'].iloc[::step],rotation=40,ha='right');ax.set_ylabel('有效停机小时合计')
    save('monthly','按报修月份汇总停机时长（全量有效维修）',monthly)
    save('workshop_count','车间维保频次（全量有效维修）',lambda ax:bar(ax,data.workshops,'所属车间','有效维修单数','有效维修单数'))
    save('workshop_cost','车间维修费用（排除缺失及负费用）',lambda ax:bar(ax,data.workshops,'所属车间','维修费用合计元','维修费用（元）'))
    def frequency(ax):
        top=data.device_frequency.head(20).iloc[::-1]
        ax.barh(top['设备编号'],top['有效维修次数'],color='#147d92')
        ax.set_xlabel('有效累计维修次数（同次数按设备编号排序）')
        ax.tick_params(axis='y',labelsize=8)
    save('device_frequency','各设备维保频次：全局前20台（完整设备见表格）',frequency)
    save('category_count','各类别维保频次',lambda ax:bar(ax,data.category_operations,'设备类别','有效维修单数','有效维修单数'))
    save('category_cost','各类别维修费用',lambda ax:bar(ax,data.category_operations,'设备类别','维修费用合计元','维修费用（元）'))
    save('methods','维修方式分布',lambda ax:bar(ax,data.methods,'维修方式','有效维修次数','有效维修次数'))
    save('retirement','已报废设备原因分布（含周期不可计算设备）',lambda ax:bar(ax,data.retirement,'报废原因','设备数','设备数'))
    def heatmap(ax,frame,label):
        if frame.empty or not len(frame.columns):
            ax.text(.5,.5,'无有效数据',ha='center');return
        im=ax.imshow(frame.to_numpy(),aspect='auto',cmap='Blues')
        ax.set_xticks(range(len(frame.columns)),frame.columns,rotation=30,ha='right')
        ax.set_yticks(range(len(frame.index)),frame.index)
        ax.figure.colorbar(im,ax=ax,label=label)
        ax.grid(False)
    save('category_faults','设备类别与故障类型分布',lambda ax:heatmap(ax,data.category_faults,'有效维修次数'))
    save('seasonal','各日历月停机时长（跨年汇总，未校正月份覆盖）',lambda ax:bar(ax,data.seasonal,'月份序号','已知有效停机小时','已知有效停机小时'))
    save('seasonal_category','类别季节分布（跨年按日历月累计次数）',lambda ax:heatmap(ax,data.seasonal_category,'有效维修次数'))
    save('category_fault_shares','类别内故障占比（每行分母为该类别全部有效维修）',lambda ax:heatmap(ax,data.category_fault_shares,'类别内占比（%）'))
    def seasonal_hours(ax):
        from analysis_dimensions import FOCUS_WINDOWS
        for category in FOCUS_WINDOWS:
            part=data.category_monthly.loc[data.category_monthly['设备类别'].eq(category)]
            ax.plot(part['月份序号'],part['已知停机小时'],marker='o',markersize=3,label=category)
        ax.axvspan(6.5,9.5,color='#ffdf85',alpha=.25)
        ax.axvspan(.5,2.5,color='#b8d9ff',alpha=.25)
        ax.set_xticks(range(1,13));ax.set_xlabel('日历月（跨年累计；蓝色1—2月、黄色7—9月）')
        ax.set_ylabel('已知有效停机小时');ax.legend(fontsize=8,ncol=3)
    save('seasonal_hours','重点类别各月停机时长（缺失不补零）',seasonal_hours)
    def seasonal_compare(ax,metric,ylabel):
        import numpy as np
        frame=data.seasonal_focus;x=np.arange(len(frame));width=.36
        ax.bar(x-width/2,frame['重点期'+metric],width,label='重点月份',color='#e99a35')
        ax.bar(x+width/2,frame['其余期'+metric],width,label='其余月份',color='#147d92')
        ax.set_xticks(x,frame['设备类别']+'\n'+frame['重点月份']);ax.set_ylabel(ylabel);ax.legend()
    save('seasonal_compare_count','重点季节与其余月份对比（按覆盖年月数均摊）',lambda ax:seasonal_compare(ax,'月均次数','每覆盖年月平均维修次数'))
    save('seasonal_compare_hours','重点季节停机负担对比（按覆盖年月数均摊）',lambda ax:seasonal_compare(ax,'月均已知停机小时','每覆盖年月平均已知停机小时'))
    return result
