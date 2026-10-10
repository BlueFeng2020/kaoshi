from html.parser import HTMLParser
from pathlib import Path
import shutil
import tempfile
import unittest
from app import create_app
from auth import connection, find_user, initialize
from config import read_exam_id
from processing import DEVICE_COLUMNS

ROOT=Path(__file__).resolve().parents[1]


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag=='td' and self.row is not None:self.cell=''
    def handle_data(self,text):
        if self.cell is not None:self.cell+=text
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            self.row.append(self.cell.strip());self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        shutil.copytree(ROOT/'data',cls.root/'data')
        (cls.root/'exam_id.txt').write_text('验收47',encoding='utf-8')
        cls.app=create_app(cls.root,testing=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):self.client=self.app.test_client()

    def csrf(self,client=None):
        client=client or self.client
        with client.session_transaction() as s:return s['csrf_token']

    def login(self,name='user',password='User@123456',client=None):
        client=client or self.client
        client.get('/login')
        return client.post('/login',data={'username':name,'password':password,'csrf_token':self.csrf(client)})

    def rows(self,url):
        parser=TableParser();parser.feed(self.client.get(url).get_data(as_text=True));return parser.rows

    def test_01_unauthenticated_all_business_routes_and_post(self):
        for url in ['/','/devices','/devices/SB-0001','/lifecycle','/analytics','/frequency','/report','/admin','/charts/category','/download/设备台账数据']:
            r=self.client.get(url);self.assertEqual(r.status_code,302,url);self.assertEqual(r.location,'/login')
        self.assertEqual(self.client.post('/admin',data={'username':'intruder','password':'123456'}).status_code,302)

    def test_02_login_logout_and_wrong_password(self):
        self.assertIn('用户名或密码不正确',self.login(password='wrong').get_data(as_text=True))
        self.assertEqual(self.login().status_code,302)
        self.client.get('/devices')
        r=self.client.post('/logout',data={'csrf_token':self.csrf()})
        self.assertEqual(r.status_code,302);self.assertEqual(self.client.get('/devices').status_code,302)

    def test_03_user_pages_and_direct_post_forbidden(self):
        self.login()
        for url in ['/devices','/devices/SB-0001','/lifecycle','/analytics','/frequency','/report']:
            r=self.client.get(url);self.assertEqual(r.status_code,200,url);self.assertIn('抽签序号：验收47',r.get_data(as_text=True))
        self.assertEqual(self.client.get('/admin').status_code,403)
        for payload in [{},{'csrf_token':self.csrf(),'username':'intruder','password':'123456','role':'admin'}]:
            self.assertEqual(self.client.post('/admin',data=payload).status_code,403)
        self.assertIsNone(find_user(self.app.config['DB_PATH'],username='intruder'))
        self.assertNotIn('href="/admin"',self.client.get('/devices').get_data(as_text=True))

    def test_04_filters_pagination_and_all_original_fields(self):
        self.login()
        page=self.client.get('/devices').get_data(as_text=True)
        self.assertIn('id="total-count">1080',page)
        for col in DEVICE_COLUMNS:self.assertIn(col,page)
        a=self.rows('/devices');b=self.rows('/devices?page=2')
        self.assertEqual(len(a),25);self.assertEqual(len(b),25);self.assertFalse(set(x[0] for x in a)&set(x[0] for x in b))
        all_ids=[]
        for page in range(1,12):all_ids.extend(x[0] for x in self.rows(f'/devices?size=100&page={page}'))
        self.assertEqual(len(all_ids),1080);self.assertEqual(len(set(all_ids)),1080)
        self.assertEqual(len(self.rows('/devices?q=SB-0001')),1)
        self.assertIn('没有匹配',self.client.get('/devices?q=NOT-EXIST').get_data(as_text=True))
        rows=self.rows('/devices?category=数控机床&workshop=二车间&status=在用&size=100')
        self.assertTrue(rows)
        for row in rows:self.assertEqual((row[2],row[5],row[9]),('数控机床','二车间','在用'))
        for query in ['?page=oops&size=bad','?page=-10','?size=0','?page=99999','?q=%5B']:
            self.assertEqual(self.client.get('/devices'+query).status_code,200)
        self.assertEqual(self.client.get('/devices/UNKNOWN').status_code,404)
        detail=self.client.get('/devices/SB-0001').get_data(as_text=True)
        self.assertIn('全部维修历史 · 4 条',detail);self.assertIn('WX-2024-00001',detail)

    def test_05_admin_create_login_and_restart_persistence(self):
        self.login('admin','Admin@123456');self.client.get('/admin')
        payload={'csrf_token':self.csrf(),'username':'newjudge','password':'Judge@123','role':'user'}
        self.assertEqual(self.client.post('/admin',data=payload).status_code,302)
        self.assertEqual(self.login('newjudge','Judge@123',self.app.test_client()).status_code,302)
        before=find_user(self.app.config['DB_PATH'],username='admin')['password_hash']
        restarted=create_app(self.root,testing=True,make_charts=False)
        self.assertEqual(self.login('newjudge','Judge@123',restarted.test_client()).status_code,302)
        self.assertEqual(before,find_user(restarted.config['DB_PATH'],username='admin')['password_hash'])
        with connection(self.app.config['DB_PATH']) as db:
            hashes=[r['password_hash'] for r in db.execute('SELECT password_hash FROM users')]
        self.assertTrue(all(h.startswith('scrypt:') for h in hashes))
        self.assertNotIn('Judge@123',' '.join(hashes))

    def test_06_validation_csrf_and_role(self):
        self.login('admin','Admin@123456');self.client.get('/admin')
        self.assertEqual(self.client.post('/admin',data={'username':'no_csrf','password':'123456'}).status_code,400)
        for name,password,role,message in [('admin','123456','user','用户名已存在'),('blankpass','','user','密码须为'),('badrole','123456','owner','无效角色'),('x','123456','user','用户名须为')]:
            r=self.client.post('/admin',data={'csrf_token':self.csrf(),'username':name,'password':password,'role':role})
            self.assertIn(message,r.get_data(as_text=True))

    def test_07_charts_downloads_and_local_assets(self):
        self.login()
        for name in self.app.extensions['chart_files']:
            with self.client.get('/charts/'+name) as r:
                self.assertEqual(r.status_code,200);self.assertTrue(r.data.startswith(b'\x89PNG'))
        for name in self.app.extensions['dataset'].exports:
            with self.client.get('/download/'+name) as r:
                self.assertEqual(r.status_code,200);self.assertIn('attachment',r.headers['Content-Disposition'])
        self.assertEqual(self.client.get('/download/../../runtime/accounts.sqlite3').status_code,404)
        self.assertEqual(self.client.get('/charts/missing').status_code,404)
        for name in ['lifecycle.html','analytics.html','base.html','login.html']:
            html=(ROOT/'templates'/name).read_text(encoding='utf-8')
            self.assertNotIn('https://',html);self.assertNotIn('http://',html)
        with self.client.get('/static/style.css') as r:self.assertEqual(r.status_code,200)

    def test_08_empty_account_table_only_initialization(self):
        path=self.root/'separate.sqlite3';initialize(path)
        with connection(path) as db:db.execute("DELETE FROM users WHERE username='admin'")
        initialize(path)
        self.assertIsNone(find_user(path,username='admin'))

    def test_09_dynamic_id_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'exam_id.txt'
            for value in ['../escape','','CON','A/B']:
                p.write_text(value,encoding='utf-8')
                with self.assertRaises(ValueError):read_exam_id(Path(tmp))
            p.write_text('047',encoding='utf-8');self.assertEqual(read_exam_id(Path(tmp)),'047')

    def test_10_frequency_all_devices_and_new_analysis_sections(self):
        self.login()
        identifiers=[]
        for page in range(1,45):
            identifiers.extend(r[0] for r in self.rows(f'/frequency?page={page}'))
        self.assertEqual(len(identifiers),1080)
        self.assertEqual(len(set(identifiers)),1080)
        self.assertEqual(len(self.rows('/frequency?q=SB-0001')),1)
        for row in self.rows('/frequency?category=数控机床'):self.assertEqual(row[2],'数控机床')
        html=self.client.get('/analytics').get_data(as_text=True)
        for name in ['故障类型分布','不同月份停机时长','维修方式占比','报废原因分布','不同类别设备的故障类型差异','季节与日历月份分布','类别内占比','夏季7—9月与冬季1—2月专项对比','重点设备的月份停机时长']:
            self.assertIn(name,html)
        self.assertIn('class="sidebar"',html)
        self.assertEqual(len(self.app.extensions['chart_files']),19)

    def test_11_role_is_checked_from_database_on_every_request(self):
        from auth import add_user
        add_user(self.app.config['DB_PATH'],'demoted','Demote@123','admin')
        self.login('demoted','Demote@123')
        self.assertEqual(self.client.get('/admin').status_code,200)
        with connection(self.app.config['DB_PATH']) as db:
            db.execute("UPDATE users SET role='user' WHERE username='demoted'")
        with self.client.session_transaction() as state:state['role']='admin'
        self.assertEqual(self.client.get('/admin').status_code,403)
        self.assertEqual(self.client.post('/admin',data={'role':'admin','username':'bypass','password':'123456','csrf_token':self.csrf()}).status_code,403)
        self.assertIsNone(find_user(self.app.config['DB_PATH'],username='bypass'))
        with connection(self.app.config['DB_PATH']) as db:db.execute("DELETE FROM users WHERE username='demoted'")
        self.assertEqual(self.client.get('/devices').status_code,302)

    def test_12_account_survives_real_process_restart(self):
        import subprocess,sys
        setup = '''
import sys
from app import create_app
app=create_app(sys.argv[1],testing=True,make_charts=False)
client=app.test_client();client.get('/login')
with client.session_transaction() as s:token=s['csrf_token']
assert client.post('/login',data={'username':'admin','password':'Admin@123456','csrf_token':token}).status_code==302
assert client.get('/admin').status_code==200
with client.session_transaction() as s:token=s['csrf_token']
assert client.post('/admin',data={'username':'processjudge','password':'Process@123','role':'user','csrf_token':token}).status_code==302
'''
        login = '''
import sys
from app import create_app
app=create_app(sys.argv[1],testing=True,make_charts=False)
client=app.test_client();client.get('/login')
with client.session_transaction() as s:token=s['csrf_token']
assert client.post('/login',data={'username':'processjudge','password':'Process@123','csrf_token':token}).status_code==302
assert client.get('/frequency').status_code==200
assert client.get('/admin').status_code==403
'''
        for code in [setup,login]:
            result=subprocess.run([sys.executable,'-c',code,str(self.root)],cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
