"""QA-only proxy for the managed Chrome fallback; all nonlocal resources denied.

Preserves the built app HTML while adding same-origin axe instrumentation.
All API routes are synthetic. The report/save UI stores screenshots locally.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import base64
import datetime
import json
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/qa/2026-10-02/artifacts/ux'
BASE = Path('/private/tmp/regengine-qa-ux-u2059hm8')
class LocalRedirectsOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != 'http' or target.hostname != '127.0.0.1' or target.port != 3104:
            raise urllib.error.HTTPError(request.full_url, 502, 'QA off-origin redirect blocked', headers, None)
        return super().redirect_request(request, response, code, message, headers, newurl)

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirectsOnly())
COUNTERS = {}
INSTRUMENT = r"""
const qa = {errors:[], csp:[], requests:[], startedAt:new Date().toISOString(), lcp:null, cls:0};
window.addEventListener('error',e=>qa.errors.push(e.message));
window.addEventListener('securitypolicyviolation',e=>qa.csp.push({directive:e.violatedDirective,uri:e.blockedURI}));
try{new PerformanceObserver(l=>qa.lcp=l.getEntries().at(-1).startTime).observe({type:'largest-contentful-paint',buffered:true});}catch{}
try{new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)qa.cls+=e.value;}).observe({type:'layout-shift',buffered:true});}catch{}
window.addEventListener('load',()=>setTimeout(async()=>{
 const result=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']}});
 const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
 const report={...qa,url:location.pathname,width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,title:document.title,cameraAllowed:document.featurePolicy?.allowsFeature('camera'),headings:[...document.querySelectorAll('h1,h2,h3')].map(e=>({level:e.tagName,text:e.textContent.trim()})),inputs:[...document.querySelectorAll('input,textarea,select')].filter(visible).map(e=>({tag:e.tagName,id:e.id,type:e.type,required:e.required,labels:[...(e.labels||[])].map(l=>l.textContent.trim())})),buttons:[...document.querySelectorAll('button')].filter(visible).map(e=>({text:e.textContent.trim(),name:e.getAttribute('aria-label'),disabled:e.disabled})),navigation:performance.getEntriesByType('navigation').map(e=>({responseStart:e.responseStart,domContentLoaded:e.domContentLoadedEventEnd,duration:e.duration})),paint:performance.getEntriesByType('paint').map(e=>({name:e.name,startTime:e.startTime})),resources:performance.getEntriesByType('resource').map(e=>({name:e.name.split('?')[0],duration:e.duration})),axe:{version:result.testEngine.version,violations:result.violations,incomplete:result.incomplete,passes:result.passes.map(e=>e.id)}};
 await fetch('/__qa/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report)});
},1200));
"""
SAVE_UI = b'''<!doctype html><title>Local QA artifact saver</title><h1>Local QA artifact saver</h1><p>Only writes the named audit artifact on this localhost process.</p><form method="post" action="/__qa/screenshot"><label>Name <input name="name" required></label><label>Screenshot bytes <textarea name="data" required></textarea></label><button>Save screenshot</button></form>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(datetime.datetime.now(datetime.timezone.utc).isoformat(), fmt % args, flush=True)

    def send(self, status, data, kind='text/html', headers=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        for k,v in (headers or {}).items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        target = self.path.split('?',1)[0]
        if target == '/__qa/save':
            name=parse_qs(urlsplit(self.path).query).get('name',[''])[0]
            name=name if re.fullmatch('[a-zA-Z0-9_-]*',name) else ''
            return self.send(200,SAVE_UI.replace(b'name="name" required',f'name="name" required value="{name}"'.encode()))
        if target == '/__qa/frame':
            route=parse_qs(urlsplit(self.path).query).get('route',['/login'])[0]
            if route not in {'/','/login','/verify','/demo','/contact','/tools/ftl-checker'}:
                return self.send(400,b'Unsupported local QA route')
            width=parse_qs(urlsplit(self.path).query).get('width',['390'])[0]
            if width not in {'320','390','768'}:
                return self.send(400,b'Unsupported QA width')
            return self.send(200,(f'<!doctype html><title>QA constrained viewport</title><style>body{{margin:0}}iframe{{border:0;width:{width}px;height:844px}}</style><iframe title="Actual product in {width}px QA viewport" src="{route}"></iframe>').encode())
        if target == '/__qa/axe.js':
            return self.send(200,(BASE/'qa-tools/node_modules/axe-core/axe.min.js').read_bytes(),'application/javascript')
        if target == '/__qa/instrument.js':
            return self.send(200,INSTRUMENT.encode(),'application/javascript')
        if target.startswith('/api/'):
            if 'csrf' in target:
                return self.send(200,b'{"csrf_token":"synthetic-qa"}','application/json')
            return self.send(401,b'{"detail":"Synthetic QA unauthenticated response"}','application/json')
        if not target.startswith('/') or target.startswith('//'):
            return self.send(400,b'Local paths only')
        request = urllib.request.Request('http://127.0.0.1:3104'+self.path,headers={'Accept-Encoding':'identity'})
        try:
            response=OPENER.open(request,timeout=30)
        except urllib.error.HTTPError as error:
            response=error
        data=response.read()
        headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-type','transfer-encoding','connection','content-encoding','content-security-policy','set-cookie','cache-control','x-dns-prefetch-control','x-frame-options'}}
        kind=response.headers.get('content-type','application/octet-stream')
        if 'text/html' in kind:
            html=data.decode()
            html=re.sub(r'<link[^>]+(?:rel="preconnect"|rel="dns-prefetch")[^>]*>','',html)
            nonces=re.findall(r'nonce="([^\"]+)"',html)
            nonce=nonces[0] if nonces else ''
            scripts=f'<script nonce="{nonce}" src="/__qa/axe.js"></script><script nonce="{nonce}" src="/__qa/instrument.js"></script>'
            html=html.replace('</head>',scripts+'</head>')
            data=html.encode()
            headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'nonce-"+nonce+"'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'none'; worker-src 'none'; form-action 'self'; base-uri 'self'; object-src 'none'"
        headers['X-DNS-Prefetch-Control']='off'
        return self.send(response.status,data,kind,headers)

    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'))
        if length>30000000:
            return self.send(413,b'Too large')
        body=self.rfile.read(length)
        target=self.path.split('?',1)[0]
        if target=='/__qa/report':
            payload=json.loads(body)
            name=re.sub(r'[^a-zA-Z0-9_-]','_',payload['url'])+'-'+str(payload['width'])
            COUNTERS[name]=COUNTERS.get(name,0)+1
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%H%M%S%f')
            (OUT/f'chrome-axe{name}-{stamp}.json').write_text(json.dumps(payload,indent=2))
            return self.send(200,b'{"saved":true}','application/json')
        if target=='/__qa/screenshot':
            from urllib.parse import parse_qs
            values=parse_qs(body.decode())
            name=values['name'][0]
            if not re.fullmatch('[a-zA-Z0-9_-]+',name):
                return self.send(400,b'Invalid artifact name')
            raw=base64.b64decode(values['data'][0],validate=True)
            if not raw.startswith(b'\xff\xd8'):
                return self.send(400,b'Expected JPEG screenshot')
            (OUT/(name+'.jpg')).write_bytes(raw)
            return self.send(200,('<h1>Saved '+name+'.jpg</h1>').encode())
        if target.startswith('/api/'):
            if target=='/api/contact':
                return self.send(503,b'{"detail":"Synthetic QA service unavailable"}','application/json')
            if 'proof' in target:
                return self.send(429,b'{"detail":"Synthetic QA rate limit"}','application/json')
            return self.send(503,b'{"detail":"Synthetic QA service unavailable"}','application/json')
        return self.send(404,b'No such QA endpoint')

server=ThreadingHTTPServer(('127.0.0.1',3105),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
import time
deadline=time.monotonic()+1200
while time.monotonic()<deadline and not (BASE/'stop-proxy-v2').exists():
    time.sleep(.25)
server.shutdown()
server.server_close()
print('QA proxy stopped')
