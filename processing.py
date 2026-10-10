"""Deterministic cleaning. Original business columns survive; no source CSV is written."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from config import CUTOFF
from domain_rules import expected_fault_type

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
        self.reconcile()
        self.refresh_flags()
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
        r['故障类型原值'] = self.raw[REPAIR_FILE]['故障类型']
        suggested = r['故障现象描述'].map(expected_fault_type)
        conflict = suggested.notna() & r['故障类型'].ne('未分类') & r['故障类型'].ne(suggested)
        self.issue(REPAIR_FILE,'故障类型',conflict,'故障现象与类型疑似不一致','精确短语规则识别；原类型留存；归入未分类并列入待复核，不臆断改成候选类型')
        r['故障类型处理依据'] = ''
        r.loc[conflict,'故障类型处理依据'] = '现象“'+r.loc[conflict,'故障现象描述']+'”按本地词典候选为“'+suggested.loc[conflict]+'”；与原类型不符，待人工复核'
        self.fault_review = r.loc[conflict,['维修单号','设备编号','故障现象描述','故障类型原值','故障类型处理依据']].copy()
        self.fault_review['候选故障类型'] = suggested.loc[conflict]
        self.fault_review['清洗后故障类型'] = '未分类'
        r.loc[conflict,'故障类型'] = '未分类'
        self.valid_repair = ~(self.orphan | ambiguous | early | reverse | report.isna() | finish.isna() | repair_start.isna() | r['维修单号'].duplicated(keep=False))
        end = pd.Series(pd.NaT,index=d.index,dtype='datetime64[ns]')
        end.loc[d['设备状态'].eq('在用')] = pd.Timestamp(CUTOFF)
        end.loc[d['设备状态'].eq('已报废')] = retired
        years = (end-start).dt.days/365.25
        self.issue(DEVICE_FILE,'投用日期',d['设备状态'].eq('在用') & years.lt(0),'在用投用晚于截止日','保留；排除截至截止日的周期')
        self.years = years.where(years.ge(0) & unique)
        self.lifecycle_valid = self.years.notna()

    def refresh_flags(self):
        d,r = self.devices,self.repairs
        for source,frame in [(DEVICE_FILE,d),(REPAIR_FILE,r)]:
            frame['数据质量标记'] = ['；'.join(dict.fromkeys(items)) for items in self.flags[source]]
            frame['抽签序号'] = self.exam_id

    def reconcile(self):
        """Compare raw sums without hiding missing values, then recompute clean totals."""
        d,r = self.devices,self.repairs
        keys = d['设备编号']
        ambiguous = keys.eq('') | keys.duplicated(keep=False)
        all_counts = r.groupby('设备编号').size()
        clean_counts = r.loc[self.valid_repair].groupby('设备编号').size()
        check = d[['设备编号','设备名称']].copy()
        for field,source in [('累计维修次数',None),('累计停机时长(小时)','停机时长(小时)'),('累计维修费用(元)','维修费用(元)')]:
            original = self.numbers[DEVICE_FILE,field]
            if source is None:
                raw_total = keys.map(all_counts).fillna(0).astype(float)
                clean_total = keys.map(clean_counts).fillna(0).astype(float)
                missing = pd.Series(0,index=d.index)
            else:
                values = self.numbers[REPAIR_FILE,source]
                raw_sum = values.groupby(r['设备编号']).sum(min_count=1)
                raw_total = keys.map(raw_sum).where(keys.isin(all_counts.index),0)
                valid_values = values.loc[self.valid_repair]
                valid_keys = r.loc[self.valid_repair,'设备编号']
                valid_sum = valid_values.groupby(valid_keys).sum(min_count=1)
                valid_n = valid_values.groupby(valid_keys).count()
                missing = keys.map(all_counts-values.groupby(r['设备编号']).count()).fillna(0)
                clean_missing = keys.map(clean_counts-valid_n).fillna(0)
                clean_total = keys.map(valid_sum).where(keys.isin(clean_counts.index),0).mask(clean_missing.gt(0))
            comparable = original.notna() & raw_total.notna() & missing.eq(0) & ~ambiguous
            mismatch = comparable & ~np.isclose(original,raw_total,rtol=0,atol=1e-6,equal_nan=False)
            status = pd.Series('一致',index=d.index)
            status.loc[missing.gt(0)] = '明细缺失或无效，无法完整核验'
            status.loc[original.isna()] = '台账值缺失或无效'
            status.loc[ambiguous] = '设备编号无效或重复，无法关联'
            status.loc[mismatch] = '与原始明细汇总不一致'
            self.issue(DEVICE_FILE,field,mismatch,f'{field}与原始维修汇总不一致','原值及对账证据留存；清洗台账改用有效维修明细重算值')
            self.issue(DEVICE_FILE,field,missing.gt(0),f'{field}明细不完整','不利用台账差额反推缺失记录；清洗后累计值在有效明细仍不完整时留空')
            clean_total = clean_total.mask(ambiguous)
            changed = ~np.isclose(original,clean_total,rtol=0,atol=1e-6,equal_nan=True)
            self.issue(DEVICE_FILE,field,changed,f'{field}按清洗明细重算','保留原始台账及对账明细；有效记录完整时重算，否则留空；无有效维修时为真实零')
            check[field+'原值'] = original
            check[field+'原始明细已知合计'] = raw_total
            check[field+'原始明细缺失数'] = missing.astype(int)
            check[field+'核验结论'] = status
            check[field+'清洗后值'] = clean_total
            d[field] = clean_total.map(lambda value:'' if pd.isna(value) else f'{value:g}')
        # Recent date must match the retained, valid repair records as well.
        recent = self.dates[REPAIR_FILE,'报修日期'].loc[self.valid_repair].groupby(r.loc[self.valid_repair,'设备编号']).max()
        updated = keys.map(recent).dt.strftime('%Y-%m-%d').fillna('').mask(ambiguous,'')
        self.issue(DEVICE_FILE,'最近维修日期',d['最近维修日期'].ne(updated),'最近维修日期按清洗明细重算','以保留的有效维修记录最新报修日期为准；原值记录于审计')
        d['最近维修日期'] = updated
        self.reconciliation = check

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
        raw_types = self.raw[REPAIR_FILE]['故障类型'].str.strip().replace('','未分类')
        self.faults = raw_types.groupby(raw_types).size().rename('原始维修次数').reset_index()
        valid_faults = r.loc[self.valid_repair].groupby('故障类型').size()
        self.faults['有效维修次数'] = self.faults['故障类型'].map(valid_faults).fillna(0).astype(int)
        self.faults['原始次数占比(%)'] = self.faults['原始维修次数']/max(len(r),1)*100
        self.faults['有效次数占比(%)'] = self.faults['有效维修次数']/max(int(self.valid_repair.sum()),1)*100
        self.faults = self.faults.sort_values('有效维修次数',ascending=False)
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
        self.analyze_extensions(work)
        ledger_counts = self.numbers[DEVICE_FILE,'累计维修次数']
        mismatch = ledger_counts.ne(life['原始关联维修单数'])
        self.summary = {
            '抽签序号':self.exam_id,'业务截止日':CUTOFF,
            '台账清洗前行数':len(d),'台账清洗后行数':len(d),'台账原始列数':len(self.raw[DEVICE_FILE].columns),
            '维修清洗前行数':len(r),'维修清洗后行数':int(self.valid_repair.sum()),'维修原始列数':len(self.raw[REPAIR_FILE].columns),
            '在用设备数':int(d['设备状态'].eq('在用').sum()),'已报废设备数':int(d['设备状态'].eq('已报废').sum()),
            '原始未维修设备数':int(life['原始关联维修单数'].eq(0).sum()),
            '周期有效设备数':int(self.lifecycle_valid.sum()),'周期排除设备数':int((~self.lifecycle_valid).sum()),
            '有效维修单数':int(self.valid_repair.sum()),'无效维修单数':int((~self.valid_repair).sum()),
            '晚于截止日报修数':int(report_dates.gt(pd.Timestamp(CUTOFF)).sum()),
            '截止日有效维修单数':int(life['截止日有效维修单数'].sum()),
            '孤立维修单数':int(self.orphan.sum()),'台账维修次数与原始关联不一致设备数':int(mismatch.sum()),
            'Pearson相关系数':self.correlation,'相关有效样本数':len(self.correlation_data),
            '故障类型疑似矛盾待复核数':len(self.fault_review),
            '清洗后未分类维修数':int((r.loc[self.valid_repair,'故障类型']=='未分类').sum()),
        }
        for field in ['累计维修次数','累计停机时长(小时)','累计维修费用(元)']:
            status=self.reconciliation[field+'核验结论']
            self.summary[field+'原始对账不一致设备数']=int(status.eq('与原始明细汇总不一致').sum())
            self.summary[field+'原始对账无法完整核验设备数']=int(status.ne('一致').sum()-status.eq('与原始明细汇总不一致').sum())

    def analyze_extensions(self, work):
        d,r=self.devices,self.repairs
        valid=r.loc[self.valid_repair]
        counts=valid.groupby('设备编号').size()
        self.device_frequency=d[['设备编号','设备名称','设备类别','所属车间','设备状态']].copy()
        self.device_frequency['有效维修次数']=d['设备编号'].map(counts).fillna(0).astype(int)
        for field,source in [('已知有效停机小时','停机小时'),('已知有效费用元','费用元')]:
            sums=work.groupby('设备编号')[source].sum(min_count=1)
            self.device_frequency[field]=d['设备编号'].map(sums).where(d['设备编号'].isin(counts.index),0)
        self.device_frequency['停机缺失或无效条数']=d['设备编号'].map(work['停机小时'].isna().groupby(work['设备编号']).sum()).fillna(0).astype(int)
        self.device_frequency['费用缺失或无效条数']=d['设备编号'].map(work['费用元'].isna().groupby(work['设备编号']).sum()).fillna(0).astype(int)
        self.device_frequency=self.device_frequency.sort_values(['有效维修次数','设备编号'],ascending=[False,True])
        unique=d.loc[~d['设备编号'].duplicated(keep=False)].set_index('设备编号')
        work['设备类别']=work['设备编号'].map(unique['设备类别'])
        self.category_operations=work.groupby('设备类别').agg(有效维修单数=('设备编号','size'),有效费用样本数=('费用元','count'),维修费用合计元=('费用元',lambda s:s.sum(min_count=1)),平均单次费用元=('费用元','mean')).reset_index()
        self.methods=valid.groupby('维修方式').size().rename('有效维修次数').reset_index()
        self.methods['占比(%)']=self.methods['有效维修次数']/max(len(valid),1)*100
        retired=d.loc[d['设备状态'].eq('已报废')].copy()
        retired['报废原因']=retired['报废原因'].str.strip().replace('','未记录')
        self.retirement=retired.groupby('报废原因').size().rename('设备数').reset_index()
        self.retirement['占比(%)']=self.retirement['设备数']/max(len(retired),1)*100
        category=valid['设备编号'].map(unique['设备类别'])
        self.category_faults=pd.crosstab(category,valid['故障类型']).reindex(index=sorted(d['设备类别'].unique()),fill_value=0).rename_axis(index='设备类别')
        self.category_faults.columns.name=None
        months=self.dates[REPAIR_FILE,'报修日期'].loc[self.valid_repair].dt.month
        self.seasonal=work.assign(月份序号=months).groupby('月份序号').agg(有效维修次数=('设备编号','size'),有效停机样本数=('停机小时','count'),已知有效停机小时=('停机小时',lambda s:s.sum(min_count=1))).reindex(range(1,13))
        empty=self.seasonal['有效维修次数'].isna()
        self.seasonal.loc[empty,:]=0
        self.seasonal=self.seasonal.reset_index()
        self.seasonal_category=pd.crosstab(category,months).reindex(index=sorted(d['设备类别'].unique()),columns=range(1,13),fill_value=0).rename_axis(index='设备类别')
        self.seasonal_category.columns=[f'{m}月' for m in self.seasonal_category.columns]
        from analysis_dimensions import dimensions
        for name,value in dimensions(self.category_faults,work,self.dates[REPAIR_FILE,'报修日期'].loc[self.valid_repair]).items():
            setattr(self,name,value)

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
        tables = {'设备台账数据':self.devices,'设备维修记录':self.repairs.loc[self.valid_repair],
                  '维修剔除记录':self.repairs.loc[~self.valid_repair],
                  '故障类型待复核':self.fault_review,'累计字段对账':self.reconciliation,
                  '各设备维保频次':self.device_frequency,'类别维保统计':self.category_operations,
                  '维修方式统计':self.methods,'报废原因统计':self.retirement,
                  '类别故障分布':self.category_faults.reset_index(),'季节月份统计':self.seasonal,'类别季节分布':self.seasonal_category.reset_index(),
                  '类别故障占比':self.category_fault_shares.reset_index(),'类别首位故障':self.category_preference,
                  '典型类别故障对比':self.category_examples,
                  '类别月份停机':self.category_monthly,'重点季节对比':self.seasonal_focus,
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
            '原始输入不覆盖。清洗台账保留全部设备；清洗维修CSV剔除无效关联、重复单号或时间逻辑异常记录；完整剔除记录另存供追溯。',
            '原始业务列保留，新增质量标记和抽签序号；维修另存故障类型原值和规则依据。疑似类型矛盾归入未分类、单列待复核，不臆断候选类型。',
            '审计为问题事件计数，同一行可能出现多个问题，不能直接求和当作异常行数。',
            '已报废完整生命周期=报废日期-投用日期；在用已运行时长=2026-09-22-投用日期；天数/365.25。',
            '相关分析采用全量有效维修单数，包含截止日以后的记录；另提供截止日有效维修单数列，严禁混用。',
            '故障分布主图采用清洗后有效次数，原始次数仅供对照；所有运维图表采用清洗后全量有效维修，含未分类及零停机。',
            '无效关联、重复维修单、无效时间、报修早于投用、完成早于报修排除有效维修指标；负值、缺失值仅排除受影响数值指标。',
            '缺失/负费用不进入费用均值分母；缺失停机不当零，全缺失分组显示空缺；合理零停机保留。',
            '累计次数、停机、费用逐设备核验原始台账与原始明细；明细不完整标明无法完整核验。清洗台账按保留的有效明细重算，并保存原值和对账依据。',
            '累计停机或费用的有效明细存在缺失时，完整累计值留空；运维表另列已知合计及样本数；不通过汇总差额反推缺失值。',
            '故障现象核验采用domain_rules.py可审查的精确短语词典，不使用在线API、预设数量或记录编号；未收录短语不作武断更正。',
            '季节图按所有年份同一日历月累计，未校正各年月份覆盖和在用暴露量，不能据此推断季节因果或故障率。'],
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
