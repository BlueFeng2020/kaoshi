"""Deterministic cleaning. Original business columns survive; no source CSV is written."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from config import CUTOFF

DEVICE_FILE = '设备台账数据.csv'
REPAIR_FILE = '设备维修记录.csv'
DEVICE_COLUMNS = ['设备编号','设备名称','设备类别','设备型号','生产厂家','所属车间','安装位置','购置金额(万元)','投用日期','设备状态','报废日期','报废原因','累计维修次数','累计停机时长(小时)','累计维修费用(元)','最近维修日期']
REPAIR_COLUMNS = ['维修单号','设备编号','设备名称','设备类别','所属车间','报修日期','故障类型','故障现象描述','停机时长(小时)','维修方式','维修人员','维修内容','维修费用(元)','维修完成日期']


class Dataset:
    def __init__(self, data_dir, output_dir, exam_id):
        self.data_dir, self.output_dir = Path(data_dir), Path(output_dir)
        self.exam_id = exam_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.audit, self.events = [], []
        self.raw = {}
        for name, required in [(DEVICE_FILE, DEVICE_COLUMNS), (REPAIR_FILE, REPAIR_COLUMNS)]:
            path = self.data_dir / name
            frame = pd.read_csv(path, encoding='utf-8-sig', dtype=str, keep_default_na=False)
            missing = set(required) - set(frame.columns)
            if missing:
                raise ValueError(f'{name} 缺少字段：{sorted(missing)}')
            if '数据质量标记' in frame:
                raise ValueError('输入必须是原始 CSV，不能把清洗输出当作输入。')
            self.raw[name] = frame
        self.devices, self.repairs = self.raw[DEVICE_FILE].copy(), self.raw[REPAIR_FILE].copy()
        self.flags = {DEVICE_FILE: [[] for _ in range(len(self.devices))], REPAIR_FILE: [[] for _ in range(len(self.repairs))]}
        self.clean()
        self.analyze()
        self.export()

    def issue(self, source, field, mask, reason, strategy):
        mask = pd.Series(mask, index=self.raw[source].index).fillna(False).astype(bool)
        self.audit.append({'文件': source, '字段': field, '问题': reason, '数量': int(mask.sum()), '处理策略': strategy})
        raw = self.raw[source]
        for idx in raw.index[mask]:
            self.flags[source][idx].append(reason)
            self.events.append({'文件':source, 'CSV行号':int(idx)+2, '设备编号':raw.at[idx,'设备编号'].strip(), '维修单号':raw.at[idx,'维修单号'] if '维修单号' in raw else '', '字段':field, '原始值':raw.at[idx,field] if field in raw else '', '问题':reason, '处理策略':strategy})

    def clean(self):
        d, r = self.devices, self.repairs
        self.dates, self.numbers = {}, {}
        date_fields = {DEVICE_FILE:['投用日期','报废日期','最近维修日期'], REPAIR_FILE:['报修日期','维修完成日期']}
        number_fields = {DEVICE_FILE:['购置金额(万元)','累计维修次数','累计停机时长(小时)','累计维修费用(元)'], REPAIR_FILE:['停机时长(小时)','维修费用(元)']}
        for source, frame in [(DEVICE_FILE,d),(REPAIR_FILE,r)]:
            raw = self.raw[source]
            self.issue(source,'设备编号',frame['设备编号'].ne(frame['设备编号'].str.strip()),'设备编号首尾空格','去除首尾空格后关联；不改变其他业务内容')
            frame['设备编号'] = frame['设备编号'].str.strip()
            self.issue(source,'设备编号',frame['设备编号'].eq(''),'设备编号缺失','保留记录；排除关联分析')
            if source == DEVICE_FILE:
                self.issue(source,'设备编号',frame['设备编号'].duplicated(keep=False),'设备编号重复','所有同编号行排除关联和周期统计，避免多对多放大')
            else:
                self.issue(source,'维修单号',frame['维修单号'].duplicated(keep=False),'维修单号重复','保留所有重复行，重复单号不纳入有效维修指标')
            for field in date_fields[source]:
                s = frame[field].str.strip()
                parsed = pd.to_datetime(s.str.replace('/','-',regex=False), format='%Y-%m-%d', errors='coerce')
                self.dates[source,field] = parsed
                self.issue(source,field,s.str.contains('/',regex=False),'斜杠日期','可解析日期统一为 YYYY-MM-DD')
                self.issue(source,field,s.ne('') & parsed.isna(),'日期无法解析','保留原值并标记；从受影响日期指标中排除')
                frame[field] = parsed.dt.strftime('%Y-%m-%d').where(parsed.notna(),s)
            for field in number_fields[source]:
                s = frame[field].str.strip()
                num = pd.to_numeric(s, errors='coerce').astype(float)
                invalid = s.ne('') & (num.isna() | ~np.isfinite(num))
                self.issue(source,field,s.eq(''),f'{field}缺失','保持缺失；不按零填充；排除对应数值平均/求和')
                self.issue(source,field,invalid,f'{field}无效数值','保留原值供追溯；分析按缺失处理')
                self.issue(source,field,num.lt(0),f'{field}为负','保留原值；排除对应数值指标')
                self.numbers[source,field] = num.where(np.isfinite(num) & num.ge(0))
            for field, replacement in [('维修人员','未记录'),('故障类型','未分类')]:
                if field in frame:
                    missing = frame[field].str.strip().eq('')
                    self.issue(source,field,missing,f'{field}缺失',f'填充“{replacement}”，保留独立类别')
                    frame[field] = frame[field].str.strip().mask(missing,replacement)
            for field in ['设备类别','所属车间','设备名称','设备状态']:
                if field not in frame:
                    continue
                missing = frame[field].str.strip().eq('')
                self.issue(source,field,missing,f'{field}缺失','显示“未记录”；未知状态不计算周期')
                frame[field] = frame[field].str.strip().mask(missing,'未记录')
        start = self.dates[DEVICE_FILE,'投用日期']
        retired = self.dates[DEVICE_FILE,'报废日期']
        self.issue(DEVICE_FILE,'投用日期',start.isna(),'投用日期缺失或无效','排除使用周期及关联周期分析')
        self.issue(DEVICE_FILE,'报废日期',d['设备状态'].eq('已报废') & retired.isna(),'已报废但报废日期缺失或无效','不猜测日期；排除完整生命周期')
        self.issue(DEVICE_FILE,'报废日期',retired.lt(start),'报废早于投用','保留并排除周期统计')
        self.issue(DEVICE_FILE,'设备状态',~d['设备状态'].isin(['在用','已报废']),'未知设备状态','保留并排除周期统计')
        unique = d['设备编号'].ne('') & ~d['设备编号'].duplicated(keep=False)
        lookup = d.loc[unique].set_index('设备编号')
        starts = pd.Series(start.loc[unique].values,index=d.loc[unique,'设备编号'])
        report = self.dates[REPAIR_FILE,'报修日期']
        finish = self.dates[REPAIR_FILE,'维修完成日期']
        self.orphan = ~r['设备编号'].isin(d['设备编号']) | r['设备编号'].eq('')
        ambiguous = r['设备编号'].isin(d.loc[~unique,'设备编号'])
        repair_start = r['设备编号'].map(starts)
        early = report.lt(repair_start)
        reverse = finish.lt(report)
        self.issue(REPAIR_FILE,'设备编号',self.orphan,'维修设备编号不存在于台账','保留；排除设备关联及有效维修指标')
        self.issue(REPAIR_FILE,'设备编号',ambiguous,'维修关联台账编号不唯一','保留；排除有效关联指标')
        self.issue(REPAIR_FILE,'报修日期',early,'报修早于投用','保留；排除有效维修次数、费用及停机趋势')
        self.issue(REPAIR_FILE,'维修完成日期',reverse,'维修完成早于报修','保留；排除有效维修次数、费用及停机趋势')
        self.issue(REPAIR_FILE,'报修日期',report.isna(),'报修日期缺失或无效','保留；排除有效维修指标')
        self.issue(REPAIR_FILE,'维修完成日期',finish.isna(),'维修完成日期缺失或无效','保留；排除已完成维修指标')
        self.issue(REPAIR_FILE,'设备编号',~self.orphan & repair_start.isna(),'关联投用日期缺失或无效','不能核验维修时间；排除有效维修指标')
        self.issue(REPAIR_FILE,'停机时长(小时)',self.numbers[REPAIR_FILE,'停机时长(小时)'].eq(0),'零停机记录','保留零值并纳入有效停机统计，不自动判错')
        future = report.gt(pd.Timestamp(CUTOFF))
        self.issue(REPAIR_FILE,'报修日期',future,'报修晚于业务截止日','原记录保留；全量运维分析纳入，截止日维修计数排除')
        for field in ['设备类别','所属车间','设备名称']:
            mapped = r['设备编号'].map(lookup[field])
            self.issue(REPAIR_FILE,field,mapped.notna() & r[field].ne(mapped),f'维修{field}与台账不一致','原字段保留；分组关联分析以台账为准')
        self.valid_repair = ~(self.orphan | ambiguous | early | reverse | report.isna() | finish.isna() | repair_start.isna() | r['维修单号'].duplicated(keep=False))
        end = pd.Series(pd.NaT,index=d.index,dtype='datetime64[ns]')
        end.loc[d['设备状态'].eq('在用')] = pd.Timestamp(CUTOFF)
        end.loc[d['设备状态'].eq('已报废')] = retired
        years = (end-start).dt.days/365.25
        self.issue(DEVICE_FILE,'投用日期',d['设备状态'].eq('在用') & years.lt(0),'在用投用晚于截止日','保留；排除截至截止日的周期')
        self.years = years.where(years.ge(0) & unique)
        self.lifecycle_valid = self.years.notna()
        for source,frame in [(DEVICE_FILE,d),(REPAIR_FILE,r)]:
            frame['数据质量标记'] = ['；'.join(dict.fromkeys(items)) for items in self.flags[source]]
            frame['抽签序号'] = self.exam_id

    def analyze(self):
        d,r = self.devices,self.repairs
        life = d[['设备编号','设备名称','设备类别','所属车间','设备状态']].copy()
        life['使用周期(年)'] = self.years
        counts = r.loc[self.valid_repair].groupby('设备编号').size()
        raw_counts = r.groupby('设备编号').size()
        report_dates = self.dates[REPAIR_FILE,'报修日期']
        asof = r.loc[self.valid_repair & report_dates.le(pd.Timestamp(CUTOFF))].groupby('设备编号').size()
        life['有效累计维修单数'] = life['设备编号'].map(counts).fillna(0).astype(int)
        life['截止日有效维修单数'] = life['设备编号'].map(asof).fillna(0).astype(int)
        life['原始关联维修单数'] = life['设备编号'].map(raw_counts).fillna(0).astype(int)
        life['数据质量标记'] = d['数据质量标记']
        self.life = life
        self.category = self.group_life(['设备类别','设备状态'])
        self.status = self.group_life(['设备状态'])
        self.correlation_data = life.loc[self.lifecycle_valid].copy()
        x,y = self.correlation_data['使用周期(年)'],self.correlation_data['有效累计维修单数']
        corr = x.corr(y) if len(x)>1 and x.nunique()>1 and y.nunique()>1 else None
        self.correlation = float(corr) if pd.notna(corr) else None
        self.correlation_groups = self.correlation_data.groupby('设备类别',dropna=False).agg(有效设备数=('设备编号','size'),平均使用周期年=('使用周期(年)','mean'),平均维修单数=('有效累计维修单数','mean')).reset_index()
        self.faults = r.groupby('故障类型').size().rename('原始维修次数').reset_index()
        valid_faults = r.loc[self.valid_repair].groupby('故障类型').size()
        self.faults['有效维修次数'] = self.faults['故障类型'].map(valid_faults).fillna(0).astype(int)
        self.faults['原始次数占比(%)'] = self.faults['原始维修次数']/max(len(r),1)*100
        self.faults = self.faults.sort_values('原始维修次数',ascending=False)
        work = r.loc[self.valid_repair,['设备编号']].copy()
        work['月份'] = report_dates.loc[work.index].dt.strftime('%Y-%m')
        work['停机小时'] = self.numbers[REPAIR_FILE,'停机时长(小时)'].loc[work.index]
        work['费用元'] = self.numbers[REPAIR_FILE,'维修费用(元)'].loc[work.index]
        workshops = d.loc[~d['设备编号'].duplicated(keep=False)].set_index('设备编号')['所属车间']
        work['所属车间'] = work['设备编号'].map(workshops)
        self.monthly = work.groupby('月份').agg(有效维修单数=('设备编号','size'),有效停机样本数=('停机小时','count'),停机小时合计=('停机小时',lambda s:s.sum(min_count=1))).reset_index()
        self.monthly['缺失或无效停机数'] = self.monthly['有效维修单数']-self.monthly['有效停机样本数']
        self.workshops = work.groupby('所属车间').agg(有效维修单数=('设备编号','size'),有效费用样本数=('费用元','count'),维修费用合计元=('费用元',lambda s:s.sum(min_count=1)),平均单次费用元=('费用元','mean')).reset_index()
        self.workshops['缺失或无效费用数'] = self.workshops['有效维修单数']-self.workshops['有效费用样本数']
        ledger_counts = self.numbers[DEVICE_FILE,'累计维修次数']
        mismatch = ledger_counts.ne(life['原始关联维修单数'])
        self.summary = {
            '抽签序号':self.exam_id,'业务截止日':CUTOFF,
            '台账清洗前行数':len(d),'台账清洗后行数':len(d),'台账原始列数':len(self.raw[DEVICE_FILE].columns),
            '维修清洗前行数':len(r),'维修清洗后行数':len(r),'维修原始列数':len(self.raw[REPAIR_FILE].columns),
            '在用设备数':int(d['设备状态'].eq('在用').sum()),'已报废设备数':int(d['设备状态'].eq('已报废').sum()),
            '原始未维修设备数':int(life['原始关联维修单数'].eq(0).sum()),
            '周期有效设备数':int(self.lifecycle_valid.sum()),'周期排除设备数':int((~self.lifecycle_valid).sum()),
            '有效维修单数':int(self.valid_repair.sum()),'无效维修单数':int((~self.valid_repair).sum()),
            '晚于截止日报修数':int(report_dates.gt(pd.Timestamp(CUTOFF)).sum()),
            '截止日有效维修单数':int(life['截止日有效维修单数'].sum()),
            '孤立维修单数':int(self.orphan.sum()),'台账维修次数与原始关联不一致设备数':int(mismatch.sum()),
            'Pearson相关系数':self.correlation,'相关有效样本数':len(self.correlation_data),
        }

    def group_life(self, keys):
        result = self.life.groupby(keys,dropna=False).agg(设备总数=('设备编号','size'),有效样本数=('使用周期(年)','count'),平均使用周期年=('使用周期(年)','mean')).reset_index()
        result['排除数量'] = result['设备总数']-result['有效样本数']
        return result

    @property
    def interpretation(self):
        c = self.correlation
        if c is None:
            return '有效样本不足或变量无变化，无法计算 Pearson 相关系数。'
        direction = '正' if c >= 0 else '负'
        strength = '较强' if abs(c)>=0.7 else '中等' if abs(c)>=0.4 else '较弱'
        return f'本样本使用周期与有效累计维修单数呈{strength}{direction}相关（r={c:.4f}）。这是累计暴露时长的相关关系，不代表因果或年故障率；在用设备时长尚未形成完整生命周期。'

    def export(self):
        self.exports = {}
        tables = {'设备台账数据':self.devices,'设备维修记录':self.repairs,
                  '清洗审计日志':pd.DataFrame(self.audit),
                  '异常明细':pd.DataFrame(self.events,columns=['文件','CSV行号','设备编号','维修单号','字段','原始值','问题','处理策略']),
                  '生命周期设备明细':self.life,'生命周期排除明细':self.life.loc[~self.lifecycle_valid],
                  '类别周期统计':self.category,'状态周期统计':self.status,'关联分组统计':self.correlation_groups,
                  '故障类型统计':self.faults,'月度停机统计':self.monthly,'车间维保统计':self.workshops}
        for label,frame in tables.items():
            name=f'{label}_{self.exam_id}.csv'
            frame.to_csv(self.output_dir/name,index=False,encoding='utf-8-sig')
            self.exports[label]=name
        report = {'汇总':self.summary,'审计':self.audit,'说明':[
            '原始业务列和原始行全部保留；新增数据质量标记和抽签序号。无效数值/日期保留原文并标记；分析时屏蔽。',
            '审计为问题事件计数，同一行可能出现多个问题，不能直接求和当作异常行数。',
            '已报废完整生命周期=报废日期-投用日期；在用已运行时长=2026-09-22-投用日期；天数/365.25。',
            '相关分析采用全量有效维修单数，包含截止日以后的记录；另提供截止日有效维修单数列，严禁混用。',
            '故障分布原始次数保留全部记录（含未分类和异常），旁列有效次数；运维月度和车间分析采用全量有效维修记录。',
            '无效关联、重复维修单、无效时间、报修早于投用、完成早于报修排除有效维修指标；负值、缺失值仅排除受影响数值指标。',
            '缺失/负费用不进入费用均值分母；缺失停机不当零，全缺失分组显示空缺；合理零停机保留。',
            '台账累计字段保留为原始业务汇总；统计均从维修明细重新计算，不能用清洗后的明细静默覆盖原汇总。',
            '故障现象与类型是否一致需要业务复核，本程序不凭文本猜测改写故障类别。'],
            '原始文件SHA256':{name:hashlib.sha256((self.data_dir/name).read_bytes()).hexdigest() for name in self.raw},
            '周期排除设备编号':self.life.loc[~self.lifecycle_valid,'设备编号'].tolist(),
            '结论':self.interpretation}
        self.report=report
        name=f'清洗报告_{self.exam_id}.json'
        (self.output_dir/name).write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        self.exports['清洗报告JSON']=name
        name=f'清洗报告_{self.exam_id}.txt'
        content='设备维护台账数据清洗报告\n抽签序号：'+self.exam_id+'\n\n'
        content+='\n'.join(f'{k}：{v}' for k,v in self.summary.items())+'\n\n'
        content+='\n'.join(report['说明'])+'\n\n'
        content+='\n'.join(f"{x['文件']} | {x['字段']} | {x['问题']}：{x['数量']}；{x['处理策略']}" for x in self.audit)
        content+='\n\n周期排除设备：'+ '、'.join(report['周期排除设备编号'])+'\n'+self.interpretation
        (self.output_dir/name).write_text(content,encoding='utf-8-sig')
        self.exports['清洗报告TXT']=name
