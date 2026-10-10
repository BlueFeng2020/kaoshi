import argparse
from functools import wraps
import math
from pathlib import Path
import secrets
import threading
import webbrowser
import pandas as pd
from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for, jsonify
from markupsafe import Markup
from config import APP_ROOT, RESOURCE_ROOT, CUTOFF, read_exam_id, prepare_local_inputs
from processing import Dataset
from charts import generate_charts
import auth
import llm


def create_app(root=None, testing=False, make_charts=True):
    root=Path(root) if root else APP_ROOT
    prepare_local_inputs(root)
    runtime=root/'runtime';runtime.mkdir(parents=True,exist_ok=True)
    exam_id=read_exam_id(root)
    key_path=runtime/'session.key'
    if not key_path.exists():
        try:
            with key_path.open('x',encoding='ascii') as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app=Flask(__name__,template_folder=str(RESOURCE_ROOT/'templates'),static_folder=str(RESOURCE_ROOT/'static'))
    app.config.update(SECRET_KEY=key_path.read_text(encoding='ascii'),TESTING=testing,
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
                      MAX_CONTENT_LENGTH=16384,TRUSTED_HOSTS=['127.0.0.1','localhost'],
                      DB_PATH=runtime/'accounts.sqlite3',EXAM_ID=exam_id)
    auth.initialize(app.config['DB_PATH'])
    data=Dataset(root/'data',root/'output',exam_id)
    chart_dir=root/'output'/'charts'
    images=generate_charts(data,chart_dir) if make_charts else {}
    app.extensions['dataset']=data
    app.extensions['chart_files']=images
    ai_lock=threading.Lock()

    def logged_in(view):
        @wraps(view)
        def wrapped(*args,**kwargs):
            if not g.user:
                return redirect(url_for('login'))
            return view(*args,**kwargs)
        return wrapped

    def admin_only(view):
        @wraps(view)
        @logged_in
        def wrapped(*args,**kwargs):
            if g.user['role']!='admin':
                abort(403)
            return view(*args,**kwargs)
        return wrapped

    def check_csrf():
        expected=session.get('csrf_token','')
        if not expected or not secrets.compare_digest(expected.encode(),request.form.get('csrf_token','').encode()):
            abort(400,description='表单已过期或校验失败，请刷新页面后重试。')

    @app.before_request
    def load_user():
        user_id=session.get('user_id')
        g.user=auth.find_user(app.config['DB_PATH'],user_id=user_id) if user_id else None
        # Check every business route before its view executes; trust roles from SQLite only.
        if request.endpoint and request.endpoint not in ('login','static'):
            if not g.user:
                return redirect(url_for('login'))
            if request.endpoint=='admin' and g.user['role']!='admin':
                abort(403)

    @app.context_processor
    def common():
        if 'csrf_token' not in session:
            session['csrf_token']=secrets.token_hex(24)
        return dict(exam_id=exam_id,cutoff=CUTOFF,current_user=g.user,csrf_token=session['csrf_token'])

    def table(frame):
        return Markup(frame.to_html(index=False,border=0,classes='data-table',na_rep='—',float_format=lambda n:f'{n:,.3f}',escape=True))

    @app.route('/login',methods=['GET','POST'])
    def login():
        if request.method=='POST':
            check_csrf()
            user=auth.authenticate(app.config['DB_PATH'],request.form.get('username','').strip(),request.form.get('password',''))
            if user:
                session.clear();session['user_id']=user['id']
                return redirect(url_for('devices'))
            flash('用户名或密码不正确。','error')
        return render_template('login.html')

    @app.post('/logout')
    @logged_in
    def logout():
        check_csrf();session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @logged_in
    def home():
        return redirect(url_for('devices'))

    @app.get('/devices')
    @logged_in
    def devices():
        d=data.devices
        q=request.args.get('q','').strip()
        selected={key:request.args.get(key,'') for key in ['category','workshop','status']}
        matched=d
        if q:
            matched=matched.loc[matched['设备编号'].str.contains(q,case=False,regex=False)|matched['设备名称'].str.contains(q,case=False,regex=False)]
        for key,column in [('category','设备类别'),('workshop','所属车间'),('status','设备状态')]:
            if selected[key]:matched=matched.loc[matched[column].eq(selected[key])]
        size=request.args.get('size',25,type=int)
        if size not in (25,50,100):size=25
        pages=max(1,math.ceil(len(matched)/size)); page=max(1,min(request.args.get('page',1,type=int),pages))
        def page_url(n):
            return url_for('devices',q=q,size=size,page=n,**selected)
        return render_template('devices.html',rows=matched.iloc[(page-1)*size:page*size].to_dict('records'),columns=list(d.columns),total=len(d),count=len(matched),q=q,selected=selected,
            options={key:sorted(d[col].unique()) for key,col in [('category','设备类别'),('workshop','所属车间'),('status','设备状态')]},page=page,pages=pages,size=size,page_url=page_url)

    @app.get('/devices/<device_id>')
    @logged_in
    def device_detail(device_id):
        subset=data.devices.loc[data.devices['设备编号'].eq(device_id)]
        if subset.empty:abort(404)
        history=data.repairs.loc[data.repairs['设备编号'].eq(device_id)]
        return render_template('detail.html',device_id=device_id,device_table=table(subset),repair_table=table(history),repair_count=len(history),life_table=table(data.life.loc[data.life['设备编号'].eq(device_id)]))

    @app.get('/lifecycle')
    @logged_in
    def lifecycle():
        return render_template('lifecycle.html',summary=data.summary,category=table(data.category),status=table(data.status),correlation=table(data.correlation_groups),
            excluded=table(data.life.loc[~data.lifecycle_valid]),interpretation=data.interpretation,images=images,detail=table(data.life))

    @app.get('/analytics')
    @logged_in
    def analytics():
        return render_template('analytics.html',summary=data.summary,faults=table(data.faults),monthly=table(data.monthly),workshops=table(data.workshops),images=images,
            category_operations=table(data.category_operations),methods=table(data.methods),retirement=table(data.retirement),
            category_faults=table(data.category_faults.reset_index()),seasonal=table(data.seasonal),seasonal_category=table(data.seasonal_category.reset_index()),
            category_fault_shares=table(data.category_fault_shares.reset_index()),category_preference=table(data.category_preference),
            category_examples=table(data.category_examples),
            category_monthly=table(data.category_monthly),seasonal_focus=table(data.seasonal_focus),season_observation=data.season_observation,
            focus_conclusions=data.seasonal_focus[['设备类别','重点月份','数据结论']].to_dict('records'))

    @app.get('/frequency')
    @logged_in
    def frequency():
        frame=data.device_frequency
        q=request.args.get('q','').strip()
        category=request.args.get('category','')
        if q:
            frame=frame.loc[frame['设备编号'].str.contains(q,regex=False,case=False)|frame['设备名称'].str.contains(q,regex=False,case=False)]
        if category:frame=frame.loc[frame['设备类别'].eq(category)]
        pages=max(1,math.ceil(len(frame)/25));page=max(1,min(request.args.get('page',1,type=int),pages))
        def page_url(n):return url_for('frequency',q=q,category=category,page=n)
        return render_template('frequency.html',detail=table(frame.iloc[(page-1)*25:page*25]),count=len(frame),total=len(data.device_frequency),q=q,
            category=category,categories=sorted(data.devices['设备类别'].unique()),page=page,pages=pages,page_url=page_url,
            zero_count=int(data.device_frequency['有效维修次数'].eq(0).sum()))

    @app.get('/report')
    @logged_in
    def report():
        return render_template('report.html',report=data.report,audit=table(pd.DataFrame(data.audit)),excluded=table(data.life.loc[~data.lifecycle_valid]),exports=data.exports,
            fault_review=table(data.fault_review),rejected=table(data.repairs.loc[~data.valid_repair]),reconciliation=table(data.reconciliation))

    @app.get('/ai')
    @logged_in
    def ai():
        return render_template('ai.html',configured=bool(llm.read_key(runtime)))

    @app.post('/ai/settings')
    @admin_only
    def ai_settings():
        check_csrf()
        try:
            llm.save_key(runtime,request.form.get('api_key',''))
            flash('API 密钥已保存到本机 runtime 目录；不会显示或随交付文件打包。','success')
        except ValueError as exc:
            flash(str(exc),'error')
        return redirect(url_for('ai'))

    @app.post('/ai/analyze')
    @logged_in
    def ai_analyze():
        import json
        check_csrf()
        question=request.form.get('question','').strip()
        if not question or len(question)>2000:
            return jsonify(error='请输入 1—2000 字的问题。'),400
        if not ai_lock.acquire(blocking=False):
            return jsonify(error='已有分析正在进行，请完成后再试。'),429
        try:
            history=json.loads(request.form.get('history','[]'))
            context=llm.context_for(data,request.form.get('device_id','').strip())
            return jsonify(llm.analyze(llm.read_key(runtime),context,question,history))
        except (ValueError,TypeError):
            return jsonify(error='问题或设备编号无效，请检查完整设备编号和对话内容。'),400
        except llm.AnalysisError as exc:
            return jsonify(error=str(exc)),502
        finally:
            ai_lock.release()

    @app.get('/download/<label>')
    @logged_in
    def download(label):
        if label not in data.exports:abort(404)
        return send_from_directory(data.output_dir,data.exports[label],as_attachment=True)

    @app.get('/charts/<key>')
    @logged_in
    def chart(key):
        if key not in images:abort(404)
        return send_from_directory(chart_dir,images[key],max_age=0)

    @app.route('/admin',methods=['GET','POST'])
    @admin_only
    def admin():
        if request.method=='POST':
            check_csrf()
            try:
                auth.add_user(app.config['DB_PATH'],request.form.get('username',''),request.form.get('password',''),request.form.get('role','user'))
                flash('账号创建成功，可退出后使用新账号登录。','success')
                return redirect(url_for('admin'))
            except ValueError as exc:
                flash(str(exc),'error')
        return render_template('admin.html',users=auth.list_users(app.config['DB_PATH']))

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(400)
    def error(exc):
        return render_template('error.html',code=exc.code,message='普通用户无权进行账号管理。' if exc.code==403 else exc.description),exc.code

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; img-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if request.endpoint!='static':response.headers['Cache-Control']='no-store'
        return response
    return app


def main():
    parser=argparse.ArgumentParser(description='设备维护台账数据分析网页系统')
    parser.add_argument('--prepare',action='store_true',help='清洗、生成图表后退出')
    parser.add_argument('--no-browser',action='store_true',help='不自动打开浏览器')
    args=parser.parse_args()
    try:
        app=create_app()
        print(f"抽签序号：{app.config['EXAM_ID']}；数据、清洗结果和图表已准备。",flush=True)
        if args.prepare:return
        # Bind synchronously before opening the browser, so port conflicts are reported.
        from werkzeug.serving import make_server
        server=make_server('127.0.0.1',8765,app,threaded=True)
        print('请访问 http://127.0.0.1:8765 ；按 Ctrl+C 退出服务。',flush=True)
        if not args.no_browser:
            threading.Timer(0.8,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
        try:server.serve_forever()
        finally:server.server_close()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'启动失败：{exc}\n检查 data 文件、exam_id.txt 和所在目录写入权限。',flush=True)
        raise


if __name__=='__main__':
    main()
