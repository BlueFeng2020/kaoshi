import hashlib
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from processing import Dataset, DEVICE_FILE, REPAIR_FILE, DEVICE_COLUMNS, REPAIR_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('*.csv')}
        cls.data=Dataset(ROOT/'data',Path(cls.tmp.name),'TEST47')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def count(self, reason, source=None):
        return sum(x['数量'] for x in self.data.audit if x['问题']==reason and (source is None or x['文件']==source))

    def test_real_shape_and_preservation(self):
        s=self.data
        self.assertEqual(s.raw[DEVICE_FILE].shape,(1080,16))
        self.assertEqual(s.raw[REPAIR_FILE].shape,(3761,14))
        self.assertEqual(list(s.devices.columns[:len(DEVICE_COLUMNS)]),DEVICE_COLUMNS)
        self.assertEqual(list(s.repairs.columns[:len(REPAIR_COLUMNS)]),REPAIR_COLUMNS)
        self.assertEqual(list(s.devices.columns[len(DEVICE_COLUMNS):]),['数据质量标记','抽签序号'])
        self.assertEqual(list(s.repairs.columns[len(REPAIR_COLUMNS):]),['数据质量标记','抽签序号'])
        self.assertEqual(s.summary['在用设备数'],870)
        self.assertEqual(s.summary['已报废设备数'],210)
        self.assertEqual(s.summary['原始未维修设备数'],170)
        self.assertEqual(self.before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data').glob('*.csv')})

    def test_expected_anomalies_and_masks(self):
        for reason,n in {'购置金额(万元)缺失':2,'维修人员缺失':75,'故障类型缺失':56,'停机时长(小时)缺失':37,'已报废但报废日期缺失或无效':1,'斜杠日期':11,'报修早于投用':3,'维修完成早于报修':2,'零停机记录':3,'报废早于投用':3}.items():
            self.assertEqual(self.count(reason),n,reason)
        for source in [DEVICE_FILE,REPAIR_FILE]:
            self.assertEqual(self.count('设备编号首尾空格',source),5)
        self.assertEqual(self.data.summary['周期排除设备数'],4)
        self.assertEqual(self.data.summary['无效维修单数'],3)
        self.assertEqual(self.data.numbers[REPAIR_FILE,'停机时长(小时)'].isna().sum(),37)
        self.assertEqual((self.data.repairs['故障类型']=='未分类').sum(),56)

    def test_real_analysis_reconciles(self):
        s=self.data
        self.assertAlmostEqual(s.correlation,0.7927106959684143,places=10)
        self.assertEqual(len(s.correlation_data),1076)
        self.assertEqual(s.summary['孤立维修单数'],0)
        self.assertEqual(s.summary['台账维修次数与原始关联不一致设备数'],0)
        self.assertEqual(s.summary['晚于截止日报修数'],4)
        self.assertEqual(s.summary['有效维修单数']-s.summary['截止日有效维修单数'],4)
        self.assertEqual(s.faults['原始维修次数'].sum(),3761)
        self.assertAlmostEqual(s.faults['原始次数占比(%)'].sum(),100)
        self.assertEqual(s.workshops['有效维修单数'].sum(),3758)
        self.assertEqual(s.monthly['有效维修单数'].sum(),3758)
        self.assertAlmostEqual(s.monthly['停机小时合计'].sum(),s.numbers[REPAIR_FILE,'停机时长(小时)'][s.valid_repair].sum())
        self.assertAlmostEqual(s.workshops['维修费用合计元'].sum(),s.numbers[REPAIR_FILE,'维修费用(元)'][s.valid_repair].sum())

    def test_exports_are_real_bom_csv_with_dynamic_id(self):
        for label,name in self.data.exports.items():
            self.assertIn('TEST47',name)
            p=Path(self.tmp.name)/name
            self.assertTrue(p.exists())
            if p.suffix=='.csv':
                self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual(len(pd.read_csv(Path(self.tmp.name)/'设备维修记录_TEST47.csv')),3761)
        for label in ['设备台账数据','设备维修记录']:
            frame=pd.read_csv(Path(self.tmp.name)/f'{label}_TEST47.csv',encoding='utf-8-sig',dtype=str)
            self.assertTrue(frame['抽签序号'].eq('TEST47').all())


class EdgeCaseTests(unittest.TestCase):
    def test_invalid_rows_retained_and_metric_specific_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'data'; source.mkdir()
            d=pd.read_csv(ROOT/'data'/DEVICE_FILE,encoding='utf-8-sig',dtype=str,keep_default_na=False).iloc[:2].copy()
            r=pd.read_csv(ROOT/'data'/REPAIR_FILE,encoding='utf-8-sig',dtype=str,keep_default_na=False).iloc[:6].copy()
            d['投用日期']='2020/01/01'; d['设备状态']='在用'; d['报废日期']=''
            r['设备编号']=d.iloc[0]['设备编号']; r['报修日期']='2024-01-01'; r['维修完成日期']='2024-01-02'
            r['停机时长(小时)']='5'; r['维修费用(元)']='10'
            r.loc[r.index[0],'报修日期']='not-a-date'
            r.loc[r.index[1],'设备编号']='UNKNOWN'
            r.loc[r.index[2],'停机时长(小时)']='-1'
            r.loc[r.index[3],'维修费用(元)']='-8'
            r.loc[r.index[4],'停机时长(小时)']=''
            r.loc[r.index[5],'停机时长(小时)']='0'
            d.to_csv(source/DEVICE_FILE,index=False,encoding='utf-8-sig');r.to_csv(source/REPAIR_FILE,index=False,encoding='utf-8-sig')
            s=Dataset(source,root/'out','EDGE')
            self.assertEqual(len(s.repairs),6)
            self.assertEqual(s.valid_repair.sum(),4)
            self.assertEqual(s.monthly['有效停机样本数'].sum(),2)
            self.assertEqual(s.monthly['停机小时合计'].sum(),5)
            self.assertEqual(s.workshops['有效费用样本数'].sum(),3)
            self.assertEqual(s.workshops['维修费用合计元'].sum(),30)
            self.assertEqual(s.repairs.iloc[0]['报修日期'],'not-a-date')


if __name__=='__main__':
    unittest.main()
