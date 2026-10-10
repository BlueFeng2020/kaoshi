"""Descriptive category and season comparisons from valid, locally joined repairs."""
import pandas as pd

FOCUS_WINDOWS = {
    '制冷机组': (7, 8, 9), '空压机': (7, 8, 9),
    '变压器': (7, 8, 9), '配电柜': (7, 8, 9), '风机': (1, 2),
}


def dimensions(fault_counts, work, dates):
    totals = fault_counts.sum(axis=1)
    shares = fault_counts.div(totals.where(totals.gt(0)), axis=0) * 100
    preference = []
    for category, row in fault_counts.iterrows():
        total = int(totals[category])
        top = int(row.max()) if total else 0
        kinds = '、'.join(str(x) for x in row.index[row.eq(top)]) if total else '无有效记录'
        preference.append({'设备类别': category, '有效维修次数': total,
                           '首位故障类型(并列全列)': kinds, '首位单类型次数': top,
                           '首位单类型占比(%)': top / total * 100 if total else float('nan'),
                           '未分类次数': int(row.get('未分类', 0))})
    preference = pd.DataFrame(preference)
    examples = []
    all_count = int(totals.sum())
    for category, kind in [('注塑机', '液压故障'), ('PLC控制柜', '控制/软件故障'), ('变压器', '外部因素')]:
        count = int(fault_counts.loc[category, kind]) if category in fault_counts.index and kind in fault_counts else 0
        total = int(totals.get(category, 0))
        global_count = int(fault_counts[kind].sum()) if kind in fault_counts else 0
        examples.append({'设备类别': category, '关注故障类型': kind, '该类型有效次数': count,
                         '类别有效总次数': total, '类别内占比(%)': count / total * 100 if total else float('nan'),
                         '全体设备该类型占比(%)': global_count / all_count * 100 if all_count else float('nan')})
    detail = work.assign(月份序号=dates.dt.month)
    grouped = detail.groupby(['设备类别', '月份序号']).agg(
        有效维修次数=('设备编号', 'size'), 有效停机样本数=('停机小时', 'count'),
        已知停机小时=('停机小时', lambda s: s.sum(min_count=1)))
    index = pd.MultiIndex.from_product([fault_counts.index, range(1, 13)], names=['设备类别', '月份序号'])
    grouped = grouped.reindex(index)
    # No repairs means zero; repairs with entirely missing hours remain NaN.
    grouped.loc[grouped['有效维修次数'].isna(), :] = 0
    grouped['停机缺失或无效条数'] = grouped['有效维修次数'] - grouped['有效停机样本数']
    monthly = grouped.reset_index()
    periods = pd.period_range(dates.min(), dates.max(), freq='M') if len(dates) else pd.PeriodIndex([], freq='M')
    focus = []
    for category, months in FOCUS_WINDOWS.items():
        frame = detail.loc[detail['设备类别'].eq(category)]
        target = frame.loc[frame['月份序号'].isin(months)]
        other = frame.loc[~frame['月份序号'].isin(months)]
        row = {'设备类别': category, '重点月份': '7—9月' if months == (7, 8, 9) else '1—2月',
               '全期有效次数': len(frame), '重点期次数占比(%)': len(target) / len(frame) * 100 if len(frame) else float('nan')}
        for label, part, coverage in [('重点期', target, int(periods.month.isin(months).sum())),
                                      ('其余期', other, int((~periods.month.isin(months)).sum()))]:
            hours = part['停机小时'].sum(min_count=1) if len(part) else 0.0
            row.update({label+'次数': len(part), label+'覆盖年月数': coverage,
                        label+'月均次数': len(part) / coverage if coverage else float('nan'),
                        label+'已知停机小时': hours,
                        label+'月均已知停机小时': hours / coverage if coverage else float('nan'),
                        label+'停机缺失数': int(part['停机小时'].isna().sum())})
        baseline = row['其余期月均次数']
        ratio = row['重点期月均次数'] / baseline if baseline > 0 else float('nan')
        row['月均次数比(重点/其余)'] = ratio
        if not len(frame) or pd.isna(ratio):
            row['数据结论'] = '样本或对照不足，不能判断月份集中程度'
        else:
            direction = '高于' if ratio > 1 else '低于' if ratio < 1 else '等于'
            row['数据结论'] = f'重点期月均维修次数{direction}其余期，为其{ratio:.2f}倍；仅作描述性比较'
        focus.append(row)
    return {'category_fault_shares': shares, 'category_preference': preference,
            'category_examples': pd.DataFrame(examples),
            'category_monthly': monthly, 'seasonal_focus': pd.DataFrame(focus),
            'season_observation': f'{periods[0]} 至 {periods[-1]}' if len(periods) else '无有效报修日期'}
