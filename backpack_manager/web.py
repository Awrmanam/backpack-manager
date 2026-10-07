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
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BackPack Manager</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#131a2e;--muted:#8fa0bf;--line:#28324d;--ok:#4ade80;--bad:#fb7185;--accent:#60a5fa}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:#f4f7ff}
main{max-width:1200px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
button,input,select{font:inherit;border:1px solid var(--line);background:#0f1629;color:#fff;border-radius:9px;padding:9px 11px}button{cursor:pointer}button.primary{background:#2563eb}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px;margin-top:18px}.card{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:16px}.row{display:flex;justify-content:space-between;gap:10px;align-items:center}.muted{color:var(--muted);font-size:13px}.ok{color:var(--ok)}.bad{color:var(--bad)}.bar{height:8px;background:#202a44;border-radius:99px;overflow:hidden;margin:8px 0}.bar>i{display:block;height:100%;background:var(--accent)}.ports{word-break:break-word}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.modal{position:fixed;inset:0;background:#0009;display:none;align-items:center;justify-content:center;padding:20px}.modal.open{display:flex}.dialog{background:var(--card);width:min(560px,100%);border:1px solid var(--line);border-radius:15px;padding:18px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fields label{display:flex;flex-direction:column;gap:5px}.full{grid-column:1/-1}.notice{padding:10px 12px;border:1px solid var(--line);border-radius:10px;margin-top:12px;color:var(--muted)}
</style></head><body><main>
<div class="top"><div><h1 style="margin:0">BackPack Manager</h1><div class="muted">سهمیه فقط دانلود است؛ آپلود رایگان است. مصرف همه پورت‌های هر Tunnel با هم محاسبه می‌شود.</div></div><button onclick="scan()">اسکن مجدد</button></div>
<div id="summary" class="notice">در حال دریافت اطلاعات…</div><div id="grid" class="grid"></div>
</main>
<div id="modal" class="modal"><div class="dialog"><div class="row"><h3 id="mt" style="margin:0"></h3><button onclick="closeModal()">✕</button></div>
<div class="fields" style="margin-top:14px">
<label>حجم<input id="quota" type="number" min="0" step="0.01" placeholder="مثلاً 2"></label><label>واحد<select id="unit"><option>TB</option><option>GB</option><option>TiB</option><option>GiB</option></select></label>
<label>مدت از الان (روز)<input id="days" type="number" min="0" step="1" placeholder="30"></label><label>جهت دانلود<select id="dir"><option value="auto">Auto</option><option value="in">bytes_in</option><option value="out">bytes_out</option></select></label>
<label class="full"><span><input id="reset" type="checkbox" checked> شروع سهمیه از صفر هنگام ذخیره</span></label>
</div><div class="actions"><button class="primary" onclick="saveLimits()">ذخیره</button><button onclick="resetUsage()">صفر کردن مصرف</button></div><div id="msg" class="notice"></div></div></div>
<script>
let rows=[], selected=null;
const fmt=n=>{if(n==null)return '—';const u=['B','KB','MB','GB','TB','PB'];let i=0,x=Number(n);while(x>=1000&&i<u.length-1){x/=1000;i++}return x.toFixed(x>=100?0:x>=10?1:2)+' '+u[i]};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function req(url,opt={}){let r=await fetch(url,{...opt,headers:{'Content-Type':'application/json',...(opt.headers||{})}});let j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.statusText);return j}
async function load(){let j=await req('/api/tunnels');rows=j.tunnels;render()}
function render(){let active=rows.filter(x=>x.active).length, managed=rows.filter(x=>x.managed).length;document.getElementById('summary').textContent=`${rows.length} تونل پیدا شد — ${active} فعال — ${managed} دارای سهمیه`;
 document.getElementById('grid').innerHTML=rows.map(x=>{let q=x.quota_bytes,used=x.usage_bytes||0,p=q?Math.min(100,used/q*100):0;let status=x.present?(x.active?'فعال':'متوقف'):'حذف/گم‌شده';let reason=x.suspended_reason?` — ${x.suspended_reason}`:'';return `<div class="card"><div class="row"><b>${esc(x.name)}</b><span class="${x.active?'ok':'bad'}">${status}${reason}</span></div><div class="muted">${esc(x.role)} · ${esc(x.transport||'—')}</div><div class="ports" style="margin-top:10px"><span class="muted">Ports:</span> ${x.ports?.length?x.ports.map(esc).join(', '):'—'}</div><div style="margin-top:12px"><div class="row"><span>دانلود سهمیه‌ای</span><b>${fmt(used)} / ${q?fmt(q):'نامحدود'}</b></div>${q?`<div class="bar"><i style="width:${p}%"></i></div>`:''}<div class="row muted"><span>دانلود خام: ${fmt(x.download_counter)}</span><span>آپلود رایگان: ${fmt(x.upload_counter)}</span></div></div><div class="muted" style="margin-top:8px">انقضا: ${x.expires_at?new Date(x.expires_at*1000).toLocaleString():'ندارد'}${x.counter_error?`<br><span class="bad">${esc(x.counter_error)}</span>`:''}</div><div class="actions"><button onclick="edit('${esc(x.name)}')">مدیریت سهمیه</button><button onclick="action('${esc(x.name)}','${x.active?'suspend':'resume'}')">${x.active?'تعلیق':'فعال‌سازی'}</button></div></div>`}).join('')}
function edit(name){selected=name;let x=rows.find(r=>r.name===name);document.getElementById('mt').textContent=name;document.getElementById('dir').value=x.direction||'auto';document.getElementById('msg').textContent='آپلود در سهمیه محاسبه نمی‌شود.';document.getElementById('modal').classList.add('open')}
function closeModal(){document.getElementById('modal').classList.remove('open')}
async function saveLimits(){try{let quota=Number(document.getElementById('quota').value||0),unit=document.getElementById('unit').value,days=Number(document.getElementById('days').value||0);await req(`/api/tunnels/${encodeURIComponent(selected)}/limits`,{method:'POST',body:JSON.stringify({quota,unit,days,direction:document.getElementById('dir').value,reset_usage:document.getElementById('reset').checked})});closeModal();await load()}catch(e){document.getElementById('msg').textContent=e.message}}
async function resetUsage(){try{await req(`/api/tunnels/${encodeURIComponent(selected)}/reset-usage`,{method:'POST',body:'{}'});closeModal();await load()}catch(e){document.getElementById('msg').textContent=e.message}}
async function action(name,a){try{await req(`/api/tunnels/${encodeURIComponent(name)}/${a}`,{method:'POST',body:'{}'});await load()}catch(e){alert(e.message)}}
async function scan(){try{await req('/api/scan',{method:'POST',body:'{}'});await load()}catch(e){alert(e.message)}}
load();setInterval(load,15000);
</script></body></html>'''


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
