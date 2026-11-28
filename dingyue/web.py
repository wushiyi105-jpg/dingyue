"""Web 入口:零依赖 http.server,单页 + JSON API。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import agent, db, llm

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>订阅 · 未来30天还要扣多少</title>
<style>
  :root{--bg:#f7f8fb;--card:#fff;--ink:#1f2937;--muted:#6b7280;--accent:#3f4b9b;--soft:#e8ebfa;
        --line:#e5e7ef;--red:#b42318;--green:#067647;--amber:#b54708;--radius:16px}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
  .wrap{max-width:980px;margin:0 auto;padding:32px 20px 80px}
  h1{font-size:26px;margin:0 0 4px} header p{color:var(--muted);margin:0 0 22px}
  .badge{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;background:var(--soft);color:var(--accent);margin-left:8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:0 1px 2px rgba(31,41,55,.04)}
  label{display:block;font-size:13px;color:var(--muted);margin:0 0 6px}
  textarea,input{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:12px;font-size:14px;font-family:inherit;background:#fff}
  textarea{line-height:1.7}
  button{background:var(--accent);color:#fff;border:none;padding:12px 22px;border-radius:12px;font-size:15px;cursor:pointer}
  .hint{color:var(--muted);font-size:12px;margin-top:8px}
  .spin{display:inline-block;width:16px;height:16px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:sp .7s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .result{display:none}.result.show{display:block}
  h3{font-size:15px;color:var(--muted);margin:20px 0 8px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:600}
  .big{font-size:22px;font-weight:700}
  ul{margin:6px 0 0 18px;padding:0}li{margin:6px 0;font-size:14px}
  .warn{color:var(--amber)}.bad{color:var(--red)}.ok{color:var(--green)}

:root{--maxw:960px;--bg:#fbf5d9;--card:#fffdf0;--ink:#1b1b18;--text:#1b1b18;--dim:#6f6a55;--line:#ddd2a7;--accent:#c65a3f;--muted:#6f6a55}
.wrap{max-width:960px}
body{background:#fbf5d9;color:#1b1b18;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
h1{color:#1b1b18}
header{max-width:960px;margin:0 auto}
input,textarea,select{background:#fff;color:#1b1b18;border-color:#ddd2a7;border-radius:2px}
button:not(.ghost):not(.tab){background:#c65a3f;color:#fff;border-radius:2px}
button.ghost{background:transparent!important;color:#c65a3f!important;border:1px solid #ddd2a7!important}
h2,h3{color:#c65a3f}
pre{background:#fafaf6;color:#1b1b18;border-color:#ddd2a7}
.item,.card{border-color:#ddd2a7;background:#fffdf0}
.k,.empty,.hint{color:#6f6a55}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:16px auto 20px;border:1px solid var(--line);background:var(--line);max-width:var(--maxw)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
pre{white-space:pre-wrap}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

header{padding:8px 0 20px;border-bottom:2px solid #1b1b18}
header h1{font-size:39px;line-height:1.24;letter-spacing:-.025em;font-weight:800}
header p{color:#746d55;font-size:14px}
.card{background:#fffdf0;border:1px solid #ddd2a7;border-radius:2px;box-shadow:none}
button{background:#c65a3f;border-radius:2px;letter-spacing:.04em}
button:hover{background:#ad4b33}
input,textarea,select{background:#fffef8;border-color:#d8cc9f;border-radius:2px;font-variant-numeric:tabular-nums}
input:focus,textarea:focus,select:focus{border-color:#c65a3f;box-shadow:0 0 0 2px #efd8cd}
.cost .cell,.cell{border-color:#ddd2a7;border-radius:2px}
.cost .cell b,.cell b,.big{font-family:"Cascadia Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.item{border-left:3px solid #c65a3f}
h3{color:#a8452f}


/* mobile-32 */

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #ddd2a7;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}

/* mobile-sticky-cta */
.mobile-cta{display:none}
@media(max-width:760px){
  body{padding-bottom:88px}
  .route{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  .route span{padding:8px 8px!important;font-size:11px!important;line-height:1.35!important}
  .route b{font-size:9px!important;margin-bottom:1px!important}
  .mobile-cta{position:fixed;left:12px;right:12px;bottom:12px;z-index:80;display:flex;
    padding:8px;border:1px solid rgba(0,0,0,.08);border-radius:12px;
    background:rgba(255,255,255,.94);backdrop-filter:blur(10px);
    box-shadow:0 10px 28px rgba(16,24,40,.18)}
  .mobile-cta button{width:100%;min-height:52px;margin:0!important;font-size:15px}
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="prod">订阅</span>未来 30 天，还要扣多少 <span class="badge" id="badge">…</span></h1>
    <p class="lede">给有多张卡和多种订阅周期的人：导入交易后，把疑似续费交给你确认，折算月均、列出下一扣费日和取消入口。</p>
  </header>
  <div class="route" aria-label="任务步骤"><span><b>01</b>贴账单交易</span><span><b>02</b>折月均与扣费日</span><span><b>03</b>处理要取消的</span></div>

  <div class="card">
    <label>账单 / 扣费记录(每行:日期 商户 金额 周期)</label>
    <textarea id="text" rows="8" placeholder="2026-10-03 爱奇艺 25 连续包月&#10;2026-10-05 腾讯视频 30 每月&#10;2026-09-20 百度网盘 30 连续包月&#10;2026-01-08 京东PLUS 198 年费"></textarea>
    <div style="margin-top:16px"><button id="btn">体检</button></div>
    <div class="hint">归一、年化、续费日、重复检测由本地算;模型只写解释,金额显示以台账为准。</div>
  </div>
  <div class="result" id="res"></div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function load(btn,on){btn.disabled=on;if(on){btn.dataset.label=btn.dataset.label||btn.textContent.trim();btn.innerHTML='<span class="spin"></span>';}else{btn.innerHTML=btn.dataset.label||btn.textContent;}}
$('#btn').onclick=async()=>{
  const el=$('#res');el.classList.remove('show');load($('#btn'),true);
  try{
    const p=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#text').value})});
    const r=await p.json(); if(r.error) throw new Error(r.error);
    let h='<div class="card"><div class="hint">'+(r.mode==='model'?'模型已连接':'离线模式')+'</div>';
    h+='<p><span class="big">'+r.total+'</span> 元/年 · '+(r.subscription_count??r.count)+' 项订阅 · 约每月 '+Math.round(r.total/12)+' 元</p>';
    if(r.one_off_count){h+='<div class="hint">另有 '+r.one_off_count+' 笔一次性支出 '+r.one_off_total+' 元,不计入年化</div>';}
    h+='<h3>台账</h3><table><tr><th>商户</th><th>类别</th><th>金额</th><th>周期</th><th>年化</th><th>下次</th></tr>';
    r.rows.forEach(x=>{h+='<tr><td>'+esc(x.merchant)+'</td><td>'+esc(x.category)+'</td><td>'+x.amount+'</td><td>'+esc(x.cycle)+'</td><td>'+x.annual+'</td><td>'+esc(x.next||'—')+'</td></tr>';});
    h+='</table>';
    if((r.flags||[]).length){h+='<h3>解析说明</h3><ul>';r.flags.forEach(f=>{h+='<li>'+esc(f.merchant)+':'+esc(f.notes.join(';'))+'</li>';});h+='</ul>';}
    if(r.duplicates.length){h+='<h3>重复订阅</h3>';r.duplicates.forEach(d=>{h+='<div class="warn">🔁 '+esc(d.category)+':'+esc(d.items.join('、'))+' —— 年化 '+d.annual+' 元</div>';});}
    h+='<h3>砍单顺序</h3><ul>';r.cut.forEach(c=>{const u=c.zero_use?'每月 0 次,直接砍':(c.per_use!=null?'单次 '+c.per_use+' 元':'未填使用次数');h+='<li>'+esc(c.merchant)+' · 年化 '+c.annual+' · '+u+'<div class="hint">'+esc(c.cancel)+'</div></li>';});h+='</ul>';
    const rf=(r.refunds||[]).filter(x=>x.open||x.note);
    if(rf.length){h+='<h3>退款窗口</h3><ul>';rf.forEach(x=>{h+='<li class="'+(x.open?'':'bad')+'">'+esc(x.merchant)+':'+(x.open?('还剩 '+x.left+' 天'):esc(x.note||'已过窗口'))+'</li>';});h+='</ul>';}
    h+='<h3>判断</h3><p>'+esc(r.summary)+'</p><ul>';r.advice.forEach(a=>h+='<li>'+esc(a)+'</li>');h+='</ul>';
    if(r.risks.length){h+='<h3>风险</h3><ul>';r.risks.forEach(x=>h+='<li class="bad">'+esc(x)+'</li>');h+='</ul>';}
    h+='</div>';el.innerHTML=h;
  }catch(e){el.innerHTML='<div class="card" style="color:#b42318">请求失败:'+esc(e.message)+'</div>';}
  el.classList.add('show');load($('#btn'),false);
};
fetch('/api/status').then(r=>r.json()).then(s=>{const b=$('#badge');
  if(s.mock){b.textContent='离线模式';b.style.background='#fee2e2';b.style.color='#b42318';}
  else{b.textContent=s.model||'模型已连接';b.style.background='#dcfce7';b.style.color='#067647';}
}).catch(()=>{});
</script>

<script>
(function(){
  var want = "体检";
  function norm(t){ return String(t||'').replace(/\s+/g,''); }
  var all=[].slice.call(document.querySelectorAll('button'));
  var src=null, fallback=null;
  for(var i=0;i<all.length;i++){
    var b=all[i];
    if(b.offsetParent===null||b.disabled) continue;
    if(!fallback) fallback=b;
    if(norm(b.textContent).indexOf(norm(want))>=0){ src=b; break; }
  }
  if(!src) src=fallback;
  if(!src) return;
  var bar=document.createElement('div'); bar.className='mobile-cta';
  var btn=src.cloneNode(true); btn.removeAttribute('id'); btn.type='button';
  btn.addEventListener('click',function(e){e.preventDefault(); src.click();});
  bar.appendChild(btn); document.body.appendChild(bar);
})();
</script>
</body></html>
"""


def _handler(cfg, force_mock, db_path):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", status)

        def _read(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            return json.loads(text) if text else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/status":
                mock = force_mock or not cfg.get("api_key")
                self._json({"mock": mock, "model": None if mock else cfg.get("model")})
            elif path == "/api/history":
                db.use(db_path)
                self._json(db.ledgers(10))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/scan":
                # 先把请求体吃掉再回 404:留着不读就关连接,Windows 上会发 RST,
                # 客户端可能在读到响应前就收到「连接被重置」。
                try:
                    left = int(self.headers.get("Content-Length", 0) or 0)
                    if left:
                        self.rfile.read(left)
                except (OSError, ValueError):
                    pass
                self._json({"error": "not found"}, 404)
                return
            try:
                body = self._read()
                db.use(db_path)
                uses = body.get("uses") or {}
                r = agent.analyze(body.get("text", ""), uses, force_mock=force_mock, config=cfg)
                if body.get("save", True):
                    r["saved_id"] = db.save(r)
                self._json(r)
            except llm.LLMError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": str(e)}, 500)

        def log_message(self, *args):
            pass

    return Handler


def serve(host="127.0.0.1", port=8000, db_path=None, force_mock=False, config=None):
    cfg = {**llm.default_config(), **(config or {})}
    httpd = ThreadingHTTPServer((host, port), _handler(cfg, force_mock, db_path))
    mode = "离线模式(未配置 key)" if (force_mock or not cfg.get("api_key")) else "模型:%s" % cfg.get("model")
    print("💳 订阅已启动:http://%s:%s  [%s]" % (host, port, mode))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
