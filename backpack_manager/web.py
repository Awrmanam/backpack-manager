from __future__ import annotations

import json
import logging
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .auth import verify_basic
from .manager import TunnelManager, bytes_from_amount

log = logging.getLogger("backpack-manager")

HTML = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BackPack Manager</title>
<style>
:root{
  color-scheme:dark;
  --bg:#090e1d;--card:#11182a;--card2:#0d1425;--muted:#8fa0bf;--text:#f5f7ff;
  --line:#27324d;--line2:#1e2942;--ok:#4ade80;--bad:#fb7185;--warn:#fbbf24;
  --accent:#60a5fa;--accent2:#3b82f6;--shadow:0 16px 44px #00000024
}
*{box-sizing:border-box}
html,body{min-height:100%}
body{
  margin:0;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Tahoma,sans-serif;
  background:
    radial-gradient(circle at 85% -10%,#17255466 0,transparent 34rem),
    radial-gradient(circle at 5% 110%,#0f766e22 0,transparent 30rem),
    var(--bg);
  color:var(--text)
}
main{max-width:1440px;margin:auto;padding:28px 30px 40px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;flex-wrap:wrap}
.brand h1{margin:0;font-size:34px;letter-spacing:-.8px}
.subtitle{color:var(--muted);font-size:14px;margin-top:7px;line-height:1.9}
button,input,select{
  font:inherit;border:1px solid var(--line);background:#0c1427;color:#fff;border-radius:10px;
  padding:10px 12px;outline:none
}
button{cursor:pointer;transition:.16s ease}
button:hover{border-color:#415276;transform:translateY(-1px)}
button.primary{background:linear-gradient(180deg,#2f6fec,#2156c8);border-color:#397af4}
button.danger{color:#fecdd3;border-color:#4b2734;background:#26131c}
button:disabled{opacity:.55;cursor:not-allowed;transform:none}
.summary{
  margin-top:20px;padding:14px 16px;border:1px solid var(--line);border-radius:14px;
  background:#0d1425cc;display:flex;align-items:center;gap:14px;flex-wrap:wrap
}
.summary strong{font-size:15px}
.summary .sep{width:1px;height:22px;background:var(--line)}
.summary .item{display:flex;align-items:center;gap:7px;color:var(--muted)}
.summary .num{color:var(--text);font-weight:750}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:16px;margin-top:18px}
.card{
  background:linear-gradient(180deg,#121a2f 0%,#10172a 100%);border:1px solid var(--line);
  border-radius:17px;padding:18px;box-shadow:var(--shadow);min-width:0
}
.card:hover{border-color:#334365}
.row{display:flex;justify-content:space-between;gap:12px;align-items:center}
.name{font-size:19px;font-weight:800;direction:ltr;text-align:left;overflow-wrap:anywhere}
.meta{color:#90a8d3;font-size:13px;margin-top:4px;direction:ltr;text-align:right}
.badge{
  display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;
  font-size:12px;font-weight:750;border:1px solid
}
.badge::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.badge.ok{color:var(--ok);border-color:#24583a;background:#10281d}
.badge.bad{color:var(--bad);border-color:#5b2b38;background:#28131c}
.badge.warn{color:var(--warn);border-color:#5b4a20;background:#281f0d}
.muted{color:var(--muted);font-size:13px}
.section{margin-top:15px;padding-top:14px;border-top:1px solid var(--line2)}
.label{font-size:13px;color:var(--muted)}
.big{font-size:20px;font-weight:820;font-variant-numeric:tabular-nums}
.metricPair{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:11px}
.metric{border:1px solid var(--line2);background:#0d1425;border-radius:12px;padding:10px 11px;min-width:0}
.metric .value{margin-top:3px;font-size:14px;font-weight:700;direction:ltr;text-align:right;overflow-wrap:anywhere}
.bar{height:9px;background:#202943;border-radius:99px;overflow:hidden;margin:10px 0 6px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent2),#60a5fa);border-radius:inherit}
.progressFoot{display:flex;justify-content:space-between;gap:10px;color:var(--muted);font-size:12px}
.portsOne{margin-top:13px;color:#e9efff}
.portsOne b{direction:ltr;display:inline-block}
.portsDetails{margin-top:13px;border:1px solid var(--line2);background:#0d1425;border-radius:12px;overflow:hidden}
.portsDetails summary{
  list-style:none;cursor:pointer;padding:10px 12px;color:#dce6fb;display:flex;
  justify-content:space-between;gap:10px;align-items:center
}
.portsDetails summary::-webkit-details-marker{display:none}
.portsDetails summary::after{content:"⌄";color:var(--muted);font-size:16px}
.portsDetails[open] summary::after{transform:rotate(180deg)}
.portList{
  border-top:1px solid var(--line2);padding:10px 12px;color:#aebbd4;font-size:13px;
  direction:ltr;text-align:left;word-break:break-word;line-height:1.7
}
.expiry{margin-top:11px;display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.expiry .date{direction:ltr;text-align:left;font-variant-numeric:tabular-nums}
.remaining.okText{color:var(--ok)}
.remaining.warnText{color:var(--warn)}
.remaining.badText{color:var(--bad)}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:15px}
.actions button{flex:1;min-width:105px}
.counterError{
  margin-top:10px;padding:9px 10px;border:1px solid #5b2b38;border-radius:10px;
  color:#fecdd3;background:#28131c;font-size:12px;direction:ltr;text-align:left;overflow-wrap:anywhere
}
.modal{
  position:fixed;inset:0;background:#030712cc;backdrop-filter:blur(5px);display:none;
  align-items:center;justify-content:center;padding:20px;z-index:20
}
.modal.open{display:flex}
.dialog{
  background:#11182a;width:min(590px,100%);border:1px solid #34415f;border-radius:18px;
  padding:19px;box-shadow:0 30px 90px #0008
}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:15px}
.fields label{display:flex;flex-direction:column;gap:6px;color:#cdd8ee;font-size:13px}
.full{grid-column:1/-1}
.checkline{display:flex!important;flex-direction:row!important;align-items:center;gap:8px!important}
.checkline input{width:auto}
.notice{
  padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin-top:12px;
  color:var(--muted);background:#0d1425;font-size:13px;line-height:1.7
}
.empty{grid-column:1/-1;text-align:center;padding:42px;color:var(--muted);border:1px dashed var(--line);border-radius:15px}
@media(max-width:700px){
  main{padding:20px 14px 32px}.brand h1{font-size:28px}.grid{grid-template-columns:1fr}
  .metricPair,.fields{grid-template-columns:1fr}.summary .sep{display:none}.summary{gap:9px 16px}
}
</style>
</head>
<body>
<main>
  <div class="top">
    <div class="brand">
      <h1>BackPack Manager</h1>
      <div class="subtitle">سهمیه فقط از دانلود کم می‌شود؛ آپلود رایگان است و مصرف همه پورت‌های هر Tunnel روی همان سهمیه مشترک جمع می‌شود.</div>
    </div>
    <button onclick="scan()">اسکن مجدد</button>
  </div>
  <div id="summary" class="summary"><span class="muted">در حال دریافت اطلاعات…</span></div>
  <div id="grid" class="grid"></div>
</main>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()">
  <div class="dialog">
    <div class="row">
      <div><div class="muted">مدیریت Tunnel</div><h3 id="mt" style="margin:3px 0 0;direction:ltr;text-align:right"></h3></div>
      <button onclick="closeModal()">✕</button>
    </div>
    <div class="fields">
      <label>حجم کل دانلود<input id="quota" type="number" min="0" step="0.01" placeholder="مثلاً 2"></label>
      <label>واحد<select id="unit"><option>TB</option><option>GB</option><option>TiB</option><option>GiB</option></select></label>
      <label>مدت اعتبار از الان (روز)<input id="days" type="number" min="0" step="1" placeholder="مثلاً 30"></label>
      <label>شمارنده دانلود<select id="dir"><option value="auto">خودکار (پیشنهادی)</option><option value="in">bytes_in</option><option value="out">bytes_out</option></select></label>
      <label class="full checkline"><input id="reset" type="checkbox" checked><span>مصرف سهمیه از زمان ذخیره از صفر شروع شود</span></label>
    </div>
    <div class="notice">آپلود هیچ‌وقت از سهمیه کم نمی‌شود. انتخاب «خودکار» روی سرور ایران معمولاً bytes_in را به‌عنوان دانلود در نظر می‌گیرد.</div>
    <div class="actions"><button class="primary" onclick="saveLimits()">ذخیره تنظیمات</button><button onclick="resetUsage()">صفر کردن مصرف</button></div>
    <div id="msg" class="notice" style="display:none"></div>
  </div>
</div>
<script>
let rows=[], selected=null, serverNow=Math.floor(Date.now()/1000);
const fmt=n=>{if(n==null)return '—';const u=['B','KB','MB','GB','TB','PB'];let i=0,x=Number(n);while(x>=1000&&i<u.length-1){x/=1000;i++}return x.toFixed(x>=100?0:x>=10?1:2)+' '+u[i]};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad=n=>String(n).padStart(2,'0');
const formatDate=ts=>{if(!ts)return 'ندارد';const d=new Date(Number(ts)*1000);return `${d.getFullYear()}/${pad(d.getMonth()+1)}/${pad(d.getDate())} - ${pad(d.getHours())}:${pad(d.getMinutes())}`};
const remainingText=ts=>{if(!ts)return {text:'بدون انقضا',cls:''};const sec=Number(ts)-serverNow;if(sec<=0)return {text:'منقضی شده',cls:'badText'};const days=Math.ceil(sec/86400);if(days===1)return {text:'1 روز باقی‌مانده',cls:'warnText'};return {text:`${days} روز باقی‌مانده`,cls:days<=3?'warnText':'okText'}};
const expandedPortCount=ports=>{let count=0;for(const raw of (ports||[])){const s=String(raw).trim();const m=s.match(/^(\d+)\s*-\s*(\d+)$/);if(m){const a=Number(m[1]),b=Number(m[2]);count+=Math.abs(b-a)+1}else if(s){count++}}return count};
const portsHtml=ports=>{const list=ports||[];if(!list.length)return '<div class="portsOne"><span class="label">پورت:</span> —</div>';const count=expandedPortCount(list);if(count===1&&list.length===1)return `<div class="portsOne"><span class="label">پورت:</span> <b>${esc(list[0])}</b></div>`;return `<details class="portsDetails"><summary><span><b>${count}</b> پورت</span><span class="muted">مشاهده پورت‌ها</span></summary><div class="portList">${list.map(esc).join(', ')}</div></details>`};
async function req(url,opt={}){const r=await fetch(url,{...opt,headers:{'Content-Type':'application/json',...(opt.headers||{})}});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.statusText);return j}
async function load(){const j=await req('/api/tunnels');rows=j.tunnels;serverNow=Number(j.now||Math.floor(Date.now()/1000));render()}
function render(){
 const active=rows.filter(x=>x.active).length,managed=rows.filter(x=>x.managed).length,suspended=rows.filter(x=>x.suspended_reason).length;
 document.getElementById('summary').innerHTML=`<strong>وضعیت سرور</strong><span class="sep"></span><span class="item"><span class="num">${rows.length}</span> Tunnel پیدا شد</span><span class="item"><span class="num">${active}</span> فعال</span><span class="item"><span class="num">${managed}</span> دارای سهمیه</span>`+(suspended?`<span class="item"><span class="num">${suspended}</span> تعلیق‌شده</span>`:'');
 if(!rows.length){document.getElementById('grid').innerHTML='<div class="empty">هیچ Tunnelی در /etc/backpack پیدا نشد.</div>';return}
 document.getElementById('grid').innerHTML=rows.map(x=>{const q=x.quota_bytes,used=Number(x.usage_bytes||0),remaining=q?Math.max(0,Number(q)-used):null,p=q?Math.min(100,used/Number(q)*100):0,percent=q?Math.min(100,Math.max(0,p)):0,status=!x.present?'حذف / گم‌شده':x.active?'فعال':x.suspended_reason?'تعلیق':'متوقف',badgeClass=x.active?'ok':(x.suspended_reason?'warn':'bad'),exp=remainingText(x.expires_at),quotaMain=q?`<div class="row"><span class="label">مصرف دانلود</span><b class="big">${fmt(used)} از ${fmt(q)}</b></div><div class="bar"><i style="width:${percent}%"></i></div><div class="progressFoot"><span>${percent.toFixed(percent>=10?0:1)}٪ مصرف شده</span><span>باقی‌مانده: ${fmt(remaining)}</span></div>`:`<div class="row"><span class="label">مصرف دانلود</span><b class="big">${fmt(used)}</b></div><div class="progressFoot" style="margin-top:7px"><span>سقف دانلود</span><span>نامحدود</span></div>`;
 return `<article class="card"><div class="row"><div style="min-width:0"><div class="name">${esc(x.name)}</div><div class="meta">${esc(x.role)} · ${esc(x.transport||'—')}</div></div><span class="badge ${badgeClass}">${status}</span></div>${portsHtml(x.ports)}<div class="section">${quotaMain}<div class="metricPair"><div class="metric"><div class="label">دانلود خام</div><div class="value">${fmt(x.download_counter)}</div></div><div class="metric"><div class="label">آپلود رایگان</div><div class="value">${fmt(x.upload_counter)}</div></div></div></div><div class="section expiry"><div><div class="label">انقضا</div><div class="date">${formatDate(x.expires_at)}</div></div><div class="remaining ${exp.cls}">${exp.text}</div></div>${x.counter_error?`<div class="counterError">${esc(x.counter_error)}</div>`:''}<div class="actions"><button onclick="edit('${esc(x.name)}')">مدیریت</button><button class="${x.active?'danger':''}" onclick="action('${esc(x.name)}','${x.active?'suspend':'resume'}')">${x.active?'تعلیق':'فعال‌سازی'}</button></div></article>`}).join('')}
function edit(name){selected=name;const x=rows.find(r=>r.name===name);document.getElementById('mt').textContent=name;document.getElementById('dir').value=x.direction||'auto';document.getElementById('quota').value='';document.getElementById('days').value='';document.getElementById('reset').checked=true;const msg=document.getElementById('msg');msg.textContent='';msg.style.display='none';document.getElementById('modal').classList.add('open')}
function closeModal(){document.getElementById('modal').classList.remove('open')}
async function saveLimits(){try{const quota=Number(document.getElementById('quota').value||0),unit=document.getElementById('unit').value,days=Number(document.getElementById('days').value||0);await req(`/api/tunnels/${encodeURIComponent(selected)}/limits`,{method:'POST',body:JSON.stringify({quota,unit,days,direction:document.getElementById('dir').value,reset_usage:document.getElementById('reset').checked})});closeModal();await load()}catch(e){const msg=document.getElementById('msg');msg.textContent=e.message;msg.style.display='block'}}
async function resetUsage(){try{await req(`/api/tunnels/${encodeURIComponent(selected)}/reset-usage`,{method:'POST',body:'{}'});closeModal();await load()}catch(e){const msg=document.getElementById('msg');msg.textContent=e.message;msg.style.display='block'}}
async function action(name,a){try{await req(`/api/tunnels/${encodeURIComponent(name)}/${a}`,{method:'POST',body:'{}'});await load()}catch(e){alert(e.message)}}
async function scan(){try{await req('/api/scan',{method:'POST',body:'{}'});await load()}catch(e){alert(e.message)}}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});load();setInterval(load,15000);
</script>
</body>
</html>'''


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler, manager: TunnelManager, auth: dict[str, Any]):
        super().__init__(addr, handler)
        self.manager = manager
        self.auth = auth


class Handler(BaseHTTPRequestHandler):
    server: AppServer

    def log_message(self, fmt, *args):
        log.info("http %s - %s", self.address_string(), fmt % args)

    def _auth_ok(self) -> bool:
        a = self.server.auth
        return verify_basic(
            self.headers.get("Authorization"),
            a["username"],
            a["salt"],
            a["password_hash"],
            int(a.get("iterations", 250000)),
        )

    def _require_auth(self) -> bool:
        if self._auth_ok():
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="BackPack Manager"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return False

    def _json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        n = min(int(self.headers.get("Content-Length") or 0), 1024 * 1024)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_GET(self):
        if not self._require_auth(): return
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers(); self.wfile.write(body); return
        if path == "/api/tunnels":
            self._json({"tunnels": self.server.manager.api_rows(), "now": int(time.time())}); return
        if path == "/healthz":
            self._json({"ok": True}); return
        self._json({"error":"not found"},404)

    def do_POST(self):
        if not self._require_auth(): return
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/scan":
                self._json({"found": self.server.manager.scan()}); return
            parts = [urllib.parse.unquote(x) for x in path.split("/") if x]
            if len(parts) != 4 or parts[:2] != ["api","tunnels"]:
                self._json({"error":"not found"},404); return
            name, action = parts[2], parts[3]
            data = self._read_json()
            if action == "limits":
                quota = float(data.get("quota") or 0)
                quota_bytes = bytes_from_amount(quota, str(data.get("unit") or "GB")) if quota > 0 else None
                days = int(data.get("days") or 0)
                expires = int(time.time()) + days*86400 if days > 0 else None
                self.server.manager.set_limits(name,quota_bytes,expires,str(data.get("direction") or "auto"),bool(data.get("reset_usage",True)))
                self._json({"ok":True}); return
            if action == "add-quota":
                amount = float(data.get("amount") or 0)
                self.server.manager.db.add_quota(name,bytes_from_amount(amount,str(data.get("unit") or "GB")))
                self._json({"ok":True}); return
            if action == "reset-usage":
                self.server.manager.reset_usage(name); self._json({"ok":True}); return
            if action == "suspend":
                self.server.manager.suspend(name); self._json({"ok":True}); return
            if action == "resume":
                self.server.manager.resume(name); self._json({"ok":True}); return
            self._json({"error":"unknown action"},404)
        except KeyError:
            self._json({"error":"tunnel not found"},404)
        except (ValueError, RuntimeError) as exc:
            self._json({"error":str(exc)},409)
        except Exception as exc:
            log.exception("request failed")
            self._json({"error":"internal error"},500)
