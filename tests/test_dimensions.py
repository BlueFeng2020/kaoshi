from pathlib import Path
import tempfile
import unittest
import pandas as pd
from analysis_dimensions import dimensions
from processing import Dataset, REPAIR_FILE

ROOT = Path(__file__).resolve().parents[1]


class DimensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Dataset(ROOT/'data', Path(cls.tmp.name), '26')

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_real_category_shares_and_examples(self):
        data = self.data
        self.assertTrue(data.category_fault_shares.sum(axis=1).sub(100).abs().lt(1e-8).all())
        valid = data.repairs.loc[data.valid_repair]
        categories = data.devices.set_index('设备编号')['设备类别']
        for row in data.category_examples.to_dict('records'):
            records = valid.loc[valid['设备编号'].map(categories).eq(row['设备类别'])]
            count = int(records['故障类型'].eq(row['关注故障类型']).sum())
            self.assertEqual(count, row['该类型有效次数'])
            self.assertAlmostEqual(row['类别内占比(%)'], count/len(records)*100)
        top = data.category_preference.set_index('设备类别')
        self.assertEqual(top.loc['注塑机','首位故障类型(并列全列)'], '液压故障')
        self.assertEqual(top.loc['PLC控制柜','首位故障类型(并列全列)'], '控制/软件故障')
        self.assertEqual(top.loc['变压器','首位故障类型(并列全列)'], '电气故障')

    def test_real_month_hours_and_season_windows(self):
        data = self.data
        self.assertEqual(len(data.category_monthly), 13*12)
        self.assertEqual(data.category_monthly['有效维修次数'].sum(), int(data.valid_repair.sum()))
        self.assertAlmostEqual(data.category_monthly['已知停机小时'].sum(), data.monthly['停机小时合计'].sum())
        self.assertEqual(data.category_monthly['停机缺失或无效条数'].sum(), 37)
        dates = data.dates[REPAIR_FILE,'报修日期'].loc[data.valid_repair]
        span = pd.period_range(dates.min(), dates.max(), freq='M')
        for row in data.seasonal_focus.to_dict('records'):
            self.assertEqual(row['重点期次数']+row['其余期次数'], row['全期有效次数'])
            self.assertEqual(row['重点期覆盖年月数']+row['其余期覆盖年月数'], len(span))
            self.assertAlmostEqual(row['重点期月均次数'], row['重点期次数']/row['重点期覆盖年月数'])
            self.assertAlmostEqual(row['月均次数比(重点/其余)'], row['重点期月均次数']/row['其余期月均次数'])

    def test_missing_zero_ties_no_samples_and_single_season(self):
        counts = pd.DataFrame({'机械故障':[1,0], '未分类':[1,0]}, index=pd.Index(['风机','空压机'], name='设备类别'))
        work = pd.DataFrame({'设备编号':['A','A'], '设备类别':['风机','风机'], '停机小时':[float('nan'),0.]})
        dates = pd.Series(pd.to_datetime(['2024-01-01','2024-02-01']))
        result = dimensions(counts, work, dates)
        self.assertTrue(result['category_fault_shares'].loc['空压机'].isna().all())
        self.assertEqual(result['category_preference'].iloc[0]['首位故障类型(并列全列)'], '机械故障、未分类')
        monthly = result['category_monthly'].set_index(['设备类别','月份序号'])
        self.assertTrue(pd.isna(monthly.loc[('风机',1),'已知停机小时']))
        self.assertEqual(monthly.loc[('风机',2),'已知停机小时'],0)
        self.assertEqual(monthly.loc[('风机',3),'已知停机小时'],0)
        focus = result['seasonal_focus'].set_index('设备类别')
        self.assertTrue(pd.isna(focus.loc['风机','月均次数比(重点/其余)']))
        empty = dimensions(counts*0, work.iloc[:0], dates.iloc[:0])
        self.assertEqual(empty['season_observation'], '无有效报修日期')
        self.assertTrue(empty['seasonal_focus']['月均次数比(重点/其余)'].isna().all())


if __name__ == '__main__': unittest.main()
