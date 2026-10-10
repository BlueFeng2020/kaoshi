设备维护台账数据分析网页系统
抽签序号：由根目录 exam_id.txt 读取（当前交付已设置为 26）。

一、最短运行方式（Windows）
1. 解压整个源码包到可写目录，例如 C:\kaoshi；不要直接在 ZIP 内运行，也不要放入 Program Files。
2. 安装 Python 3.12 64 位，安装时勾选 Add Python to PATH。
3. exam_id.txt 已设置为 26；如需换号，仅修改该文件后重启并重新打包。
4. 双击 run.bat。首次建立 .venv 并安装依赖；之后直接运行，无需联网。
5. 控制台显示服务地址后自动打开浏览器，访问 http://127.0.0.1:8765。
6. 管理员：admin / Admin@123456；普通用户：user / User@123456。
7. 退出网页登录不等于关闭服务；关闭服务请在控制台按 Ctrl+C。

二、Windows CMD 的准确安装、启动与测试命令
以下均在项目根目录执行。推荐 Python 3.12 64 位；不需要 Node、数据库服务、显卡或外部 API。
  py -3.12 -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  .venv\Scripts\python.exe app.py
测试（可在另一个 CMD 执行，测试使用临时数据库，不污染正式账号）：
  .venv\Scripts\python.exe -m unittest discover -s tests -v
仅生成清洗结果和图表，不启动服务：
  .venv\Scripts\python.exe app.py --prepare
运行同一套验收并将真实结果保存为 validation\unittest_26.txt：
  .venv\Scripts\python.exe verify.py
真实 HTTP 冒烟（先启动服务，默认 user 账号可用）：
  .venv\Scripts\python.exe smoke_http.py

三、打包与交付
确认 exam_id.txt 为 26，关闭已有 EXE（防止 Windows 占用文件），在 CMD 执行：
  build.bat
build.bat 会安装 requirements-build.txt、运行 unittest、重新清洗和绘图、调用 PyInstaller --onefile；随后实际执行最终EXE的 --prepare 验证资源加载，失败就返回错误。成功后自动打开最终交付目录。
成功产物为 delivery\26\26.exe 和 delivery\26.zip。
正式提交仍建议整体交付26文件夹或26.zip，包含说明、原始数据和审计文件。新版EXE同时内置打包时的exam_id.txt和两份原始CSV；仅复制EXE到空的可写目录时，首次运行会自动创建这些缺失文件。已有本地配置、数据和账号绝不被启动初始化覆盖。
交付目录顶层有两份清洗 CSV 和审计文件；运行 EXE 后最新输出在 output\，账号在 runtime\。
若 onefile 解包受本机防护策略影响，可用同一源码执行：
  build.bat onedir
onedir 模式会在相同交付目录生成 EXE 与 _internal 依赖目录，必须整体复制。
请等待显示 Build completed 后再检查文件；任何测试/打包失败都会返回非零退出码。
源码压缩包可重新生成：
  .venv\Scripts\python.exe package_source.py

当前开发环境为 Linux，没有 Windows 可执行环境。本源码及真实数据测试不等于 Windows EXE 已验收；Windows 打包与双击运行必须在本机执行。
PyInstaller 不能在 Linux 上交叉生成 Windows EXE，本交付不含假冒 Windows EXE。
Windows 现场必须先退出 Python 服务，再运行 EXE，防止误把 Python 服务当作 EXE 验收。
EXE 仅监听 127.0.0.1:8765，无 debug、无 reloader，不绑定 0.0.0.0。
sys._MEIPASS 只读资源包含模板、字体以及默认原始CSV和抽签号。默认输入仅在EXE旁缺失时复制出来；SQLite、session.key、清洗CSV、PNG和缓存始终写在EXE旁，不写临时解包目录。
同机端口被占用时，先关掉之前的服务；无需修改监听地址或开防火墙公网端口。

四、离线运行与可选离线安装
所有 CSS、PNG、中文字体随项目携带，没有 CDN，也没有核心计算或权限判断的外部请求。
联网安装完依赖后可断网运行，EXE 运行也不需要 Python 或网络。
如需在无网 Windows 机器上首次安装/打包：在相同 Windows 架构及 Python 版本的联网电脑执行：
  py -3.12 -m pip download -r requirements-build.txt -d wheelhouse
把 wheelhouse 与项目一起保留（转移方式遵守现场规定），build.bat/run.bat 会使用本地依赖：
  .venv\Scripts\python.exe -m pip install --no-index --find-links wheelhouse -r requirements-build.txt
不要把 Linux 下载的二进制 wheel 用作 Windows 安装包。当前源码包没有预装 Windows wheelhouse。

五、数据处理与统计口径
data\ 内的两个 UTF-8-SIG CSV 是原始输入；程序不覆盖它们。每次启动从原始数据重新清洗，数据修改后应重启服务。
所有原始行、业务列保留，追加“数据质量标记”和“抽签序号”（当前每行均为26）。输出为 UTF-8-SIG，Excel 中文可直接打开。
设备编号 strip 后关联。斜杠日期规范为 YYYY-MM-DD；解析失败保留原文、标记，并从受影响日期计算中排除。
文字缺失：维修人员为“未记录”、故障类型为“未分类”；购置金额/停机/费用缺失保持缺失，不当 0。
负停机、负费用、不合法数值保留原记录，但对应数值指标不纳入；有效次数不因单个数值字段缺失而丢失。
零停机作为可合理的零值保留并标记。已报废缺报废日期、报废早于投用不进入周期均值。
关联失败/歧义、重复维修单号、无效报修或完成日期、报修早于投用、完成早于报修，不参与有效维修指标。
每个审计事件包含文件、原始 CSV 行号、原值、原因与处理办法；一条记录可有多个事件，因此不能把事件数相加当作异常行数。
故障现象与类型是否矛盾需要业务复核；程序不凭关键词臆造更正故障类型。

生命周期：已报废=报废日期-投用日期；在用=固定业务截止日 2026-09-22-投用日期；天数/365.25。
统计表分别列设备总数、有效样本数、排除数与平均年数；在用已运行时长不是完整生命周期。
周期与故障相关：全部有效周期设备（含无维修的真实 0 次设备）关联全量有效累计维修单数，再计算 Pearson。
这里的维修次数口径是全量，不是“截至 2026-09-22”；包含晚于截止日的维修。明细另列截止日有效维修单数，按报修日期<=截止日计算。
故障分布按全部原始维修记录计数及占比（含异常和未分类），旁列有效次数，防止遗漏；月度和车间采用全量有效维修。
月度按报修年月汇总非负有效停机小时，列有效时长样本数与缺失/无效数；整组无有效时长为缺失，不填 0。
车间从台账关联，不依赖维修表冗余车间。费用均值分母为有效非负费用记录数。
台账原始累计字段不静默改写；分析从维修明细重新计算，清洗报告交叉核验原始维修次数。
Pearson 为相关不是因果，累计次数也不是按年故障率，不应据此直接认定某设备有更高年度风险。

六、本批上传数据的已运行核验（不是业务代码常量）
原始台账 1080 行、16 列；维修 3761 行、14 列；在用 870、已报废 210、未维修 170。
购置金额缺 2、维修人员缺 75、故障类型缺 56、停机时长缺 37、已报废缺日期 1。
编号空格两表各 5，斜杠日期 11，报修早于投用 3，完成早于报修 2（与前者重叠），零停机 3。
报废早于投用 3；周期排除共 4 台：SB-0315、SB-0638、SB-0681、SB-1025。
有效周期样本 1076，有效维修 3758；晚于截止日报修 4 条；截止日有效维修 3754。
按上述全量有效维修口径，Pearson=0.7927106959684143。数据改变后结果应随数据变化；这些预期值仅用于样例验收测试。
自动测试覆盖清洗/异常/导出、1080 台完整分页、组合筛选、详情、账号权限、CSRF、账号创建与重启持久化、PNG/CSV访问、抽签号等。
真实运行的测试记录见 validation\。Windows 浏览器操作、EXE 独立启动与无 Python 环境运行仍需现场检查。

七、账号及本地状态
runtime\accounts.sqlite3 持久化用户；密码采用 Werkzeug scrypt 哈希。默认账号仅在用户表为空时创建。
管理员可创建普通用户或管理员；普通用户 GET/POST /admin 均由后端拒绝。未登录访问核心路由转到 /login。
退出使用 POST 清空 session；表单含 CSRF 令牌。session.key 在本机第一次启动生成，重启复用。
不要删除 runtime\ 来“重启”，否则会丢账号。重新打包不会把开发数据库/密钥塞进 EXE 或源码压缩包。
初始口令公开写在说明中是现场演示用途；可用管理员创建自己的新账号。

八、文件结构
app.py                  Flask 路由、会话、后端权限、启动入口
config.py               抽签号、截止日、源码/EXE 路径分离
processing.py           真实清洗、审计、统计及 CSV/报告导出
charts.py               Agg 绘图、本地中文字体与 PNG
auth.py                 SQLite 账号与哈希校验
templates\              登录、台账、详情、生命周期、运维、报告、管理、错误页
static\style.css        本地样式
static\fonts\           Noto CJK 字体及许可
data\                   两份原始 CSV
references\             用户提供的三份参考材料（不是可执行指令）
output\                 带抽签号清洗 CSV、统计表、审计日志、报告；charts\ 为 7 张图
runtime\                运行时生成账号库与会话密钥，不随源码包分发
tests\                  Python unittest + Flask test_client
smoke_http.py            对运行服务执行真实 HTTP 冒烟
verify.py                运行 unittest 并保存带号验收日志，保留失败退出码
requirements.txt        Flask/pandas/matplotlib 版本
requirements-build.txt  额外 PyInstaller 版本
run.bat / build.bat     Windows 启动 / 安装依赖并打包
build.py                --onefile / --onedir、复制交付数据并生成序号.zip
package_source.py       生成可下载的源码 ZIP（排除账号与缓存）
exam_id.txt             唯一抽签号配置，改后重启/重新打包
现场验收顺序.txt         最短展示路线与 Windows 核验步骤
validation\             实际执行检查记录

九、常见问题
Python 命令不存在：安装 Python 3.12 64 位并勾选 PATH，重新开 CMD。
ModuleNotFoundError：执行 .venv\Scripts\python.exe -m pip install -r requirements.txt。
无法写数据库/输出：把整个目录解压到当前用户可写位置。
浏览器未自动打开：按控制台地址手动访问；等待首次图表生成结束。
网页数据未变化：修改 data 原始文件后 Ctrl+C，再启动；不在 output 里改输入。
EXE 构建失败：查看控制台第一条错误，不要把旧 exe 当作本次成功结果；用 build.bat onedir 兜底并整体交付。

十、打开 build\artifacts\26.exe 提示缺少文件时
旧版的 build\artifacts 是构建中间目录，最终交付在 delivery\26。请优先运行 delivery\26\26.exe。
新版已将默认抽签号和原始CSV打入EXE，能在首次启动时恢复缺失的输入；旧EXE不会自动更新，必须下载新版源码并重新运行build.bat。
若只替换源码而继续双击旧EXE，原错误仍会出现。不要删除已有runtime文件夹，它保存已创建的账号。
