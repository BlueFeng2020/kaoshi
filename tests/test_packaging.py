from pathlib import Path
import tempfile
import unittest
from config import prepare_local_inputs, read_exam_id


class FrozenInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'standalone'
        self.bundle = Path(self.temp.name)/'bundle'
        (self.bundle/'data').mkdir(parents=True)
        (self.bundle/'exam_id.txt').write_text('26\n',encoding='utf-8')
        for name in ['设备台账数据.csv','设备维修记录.csv']:
            (self.bundle/'data'/name).write_text('设备编号\nSB-0001\n',encoding='utf-8-sig')

    def tearDown(self):
        self.temp.cleanup()

    def test_bare_executable_directory_recovers_all_inputs(self):
        restored = prepare_local_inputs(self.root,self.bundle,frozen=True)
        self.assertEqual(len(restored),3)
        self.assertEqual(read_exam_id(self.root),'26')
        for name in restored:
            self.assertEqual((self.root/name).read_bytes(),(self.bundle/name).read_bytes())
        self.assertFalse((self.bundle/'runtime').exists())
        self.assertEqual(prepare_local_inputs(self.root,self.bundle,frozen=True),[])

    def test_existing_exam_id_data_and_database_are_not_overwritten(self):
        prepare_local_inputs(self.root,self.bundle,frozen=True)
        overrides = {'exam_id.txt':b'88\n','data/设备台账数据.csv':b'custom ledger',
                     'data/设备维修记录.csv':b'custom repairs','runtime/accounts.sqlite3':b'existing accounts'}
        for name,payload in overrides.items():
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
        self.assertEqual(prepare_local_inputs(self.root,self.bundle,frozen=True),[])
        for name,payload in overrides.items():
            self.assertEqual((self.root/name).read_bytes(),payload)

    def test_source_mode_does_not_seed_test_or_user_directories(self):
        self.assertEqual(prepare_local_inputs(self.root,self.bundle,frozen=False),[])
        self.assertFalse(self.root.exists())

    def test_old_bundle_fails_clearly_before_partial_initialization(self):
        (self.bundle/'data/设备维修记录.csv').unlink()
        with self.assertRaisesRegex(FileNotFoundError,'重新运行 build.bat'):
            prepare_local_inputs(self.root,self.bundle,frozen=True)
        self.assertFalse(self.root.exists())


if __name__=='__main__':
    unittest.main()
