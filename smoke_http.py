"""Read-only live HTTP smoke test. Start app.py --no-browser first; default account required."""
from http.cookiejar import CookieJar
import re
import urllib.error
import urllib.parse
import urllib.request


def main():
    base='http://127.0.0.1:8765'
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    with opener.open(base+'/devices',timeout=20) as r:
        assert r.url.endswith('/login'),'Anonymous business access must redirect to login'
        html=r.read().decode('utf-8')
    token=re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)
    body=urllib.parse.urlencode({'username':'user','password':'User@123456','csrf_token':token}).encode()
    with opener.open(base+'/login',body,timeout=20) as r:
        assert r.url.endswith('/devices')
        assert b'id="total-count">1080' in r.read()
    for path in ['/devices?q=SB-0001','/devices/SB-0001','/lifecycle','/analytics','/frequency','/ai','/report','/charts/category','/charts/correlation','/charts/device_frequency','/charts/seasonal_category']:
        with opener.open(base+path,timeout=20) as r:
            assert r.status==200
            content=r.read();assert len(content)>100
            if path.startswith('/charts/'):assert content.startswith(b'\x89PNG')
        print('PASS',path)
    try:opener.open(base+'/admin',timeout=20)
    except urllib.error.HTTPError as exc:assert exc.code==403
    else:raise AssertionError('User accessed admin')
    print('PASS live HTTP login, pages, PNG charts and backend role denial')


if __name__=='__main__':main()
