# 设备维护台账数据分析网页系统

**抽签序号：26**。统一从根目录 `exam_id.txt` 读取，页面、清洗报告、CSV、图表和 Windows 打包文件自动使用该序号。

## 下载和运行

在 GitHub 页面点击 **Code → Download ZIP**，完整解压后在项目目录操作。

1. 安装 Python 3.12（64 位，勾选 Add Python to PATH）。
2. 确认 `exam_id.txt` 内容为 `26`，双击 `run.bat`。
3. 浏览器访问 `http://127.0.0.1:8765`。所有计算、账号权限、样式和图表均在本地运行；安装依赖后可断网使用。

| 角色 | 初始用户名 | 初始密码 |
| --- | --- | --- |
| 管理员 | admin | Admin@123456 |
| 普通用户 | user | User@123456 |

账号密码以哈希存储在运行后生成的 `runtime/accounts.sqlite3`，仅在账号表为空时创建默认账号。数据库与会话密钥不会上传到本仓库。

## Windows 打包

在 Windows CMD 的项目目录执行：

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe verify.py
build.bat
```

生成 `delivery\26\26.exe` 和 `delivery\26.zip`。先停止 Python 服务，再双击 EXE 验收。`build.bat onedir` 提供目录模式兜底。

**Windows EXE 必须在 Windows 本机构建并验收；本仓库不把 Linux 测试当作 Windows EXE 运行证明。**

## 已实现和真实数据验证

- 原始台账 1080 行、16 列；维修记录 3761 行、14 列，均保留在 `data/`。
- 清洗保留原始业务列及异常行，两份清洗 CSV 的文件名带 `_26`，文件内另追加“抽签序号”列且每行均为 `26`；输出审计日志和异常明细，不覆盖原文件。
- 台账完整字段、关键词搜索、组合筛选、分页、详情和维修历史。
- 生命周期三项分析及三项运维分析，每项均有表格和本地 PNG 图表。
- 周期使用固定业务截止日 2026-09-22；4 台周期异常排除，有效样本 1076 台，实际 Pearson 约 0.7927107。
- 本地 SQLite、哈希密码、session、后端管理员权限；普通用户直接 GET/POST `/admin` 也被拒绝。
- `unittest` 自动验收和真实 HTTP 冒烟脚本，当前编号的实际结果保存在 `validation/`。

## 文件入口

- [完整运行说明](README_运行说明.txt)
- [现场验收顺序](现场验收顺序.txt)
- [交付文件清单](文件清单_26.txt)
- [清洗报告](output/清洗报告_26.txt)
- [清洗后台账 CSV](output/设备台账数据_26.csv)
- [清洗后维修 CSV](output/设备维修记录_26.csv)
- [自动测试记录](validation/unittest_26.txt)

`app.py` 为启动入口，`processing.py` 为清洗/统计实现，`auth.py` 为账号实现，`charts.py` 为绘图实现。模板、样式和中文字体位于 `templates/`、`static/`。

需要重新生成源码压缩包时，执行 `.venv\Scripts\python.exe package_source.py`，生成 `delivery\26_源码.zip`。
