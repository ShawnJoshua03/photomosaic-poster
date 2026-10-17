"""`mosaic-poster collect`: a private upload page friends open on their phones.

Photos go straight into a folder on your computer, sorted into one subfolder per
person, with a live count. No Google Drive zips, no iCloud 1,000-photo limit, nothing
to download afterwards: point the poster at the folder.

The page is protected by a random key in its link. On the same Wi-Fi it works as is;
for friends elsewhere, expose it with a tunnel (see docs/collecting-photos.md).
"""
import hmac
import json
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .formats import ARCHIVE_EXTS, IMAGE_EXTS, RAW_EXTS, VIDEO_EXTS

ALLOWED = IMAGE_EXTS | RAW_EXTS | VIDEO_EXTS | ARCHIVE_EXTS
CHUNK = 1 << 20


def _safe(name, fallback):
    name = Path(str(name).replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")[:120]
    return name or fallback


class _Collector:
    def __init__(self, dest, key, title, max_mb):
        self.dest, self.key, self.title, self.max_bytes = Path(dest), key, title, max_mb * 1e6
        self.lock = threading.Lock()
        self.dest.mkdir(parents=True, exist_ok=True)

    def stats(self):
        files = [p for p in self.dest.rglob("*") if p.is_file() and not p.name.endswith(".part")]
        people = {p.parent.name for p in files if p.parent != self.dest}
        return {"photos": len(files), "people": len(people),
                "mb": round(sum(p.stat().st_size for p in files) / 1e6, 1)}

    def target(self, who, name):
        folder = self.dest / _safe(who, "guest")
        folder.mkdir(exist_ok=True)
        base = _safe(name, "photo")
        stem, suffix = Path(base).stem, Path(base).suffix
        with self.lock:  # never overwrite: two friends both have IMG_0001.HEIC
            p, n = folder / base, 1
            while p.exists() or p.with_name(p.name + ".part").exists():
                n += 1
                p = folder / f"{stem} ({n}){suffix}"
            p.with_name(p.name + ".part").touch()
        return p


def _handler(col):
    class H(BaseHTTPRequestHandler):
        server_version = "mosaic-poster"

        def log_message(self, fmt, *args):  # keep the console readable
            pass

        def _authorized(self, q):
            given = q.get("k", [""])[0]
            return hmac.compare_digest(given.encode(), col.key.encode())

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._authorized(q):
                return self._send(403, "This link is missing its key.", "text/plain")
            if u.path == "/":
                return self._send(200, _PAGE.replace("{{TITLE}}", col.title)
                                  .replace("{{KEY}}", col.key), "text/html; charset=utf-8")
            if u.path == "/stats":
                return self._send(200, json.dumps(col.stats()))
            self._send(404, "not found", "text/plain")

        def do_POST(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path != "/upload" or not self._authorized(q):
                return self._send(403, '{"error":"forbidden"}')
            name = q.get("name", ["photo"])[0]
            if Path(name).suffix.lower() not in ALLOWED:
                return self._send(415, json.dumps({"error": f"{name}: not a photo or video"}))
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > col.max_bytes:
                return self._send(413, json.dumps({"error": "file too large or empty"}))
            path = col.target(q.get("who", ["guest"])[0], name)
            part = path.with_name(path.name + ".part")
            try:
                with open(part, "wb") as f:
                    left = length
                    while left:
                        chunk = self.rfile.read(min(CHUNK, left))
                        if not chunk:
                            raise ConnectionError("upload interrupted")
                        f.write(chunk)
                        left -= len(chunk)
                part.replace(path)
            except Exception as e:
                part.unlink(missing_ok=True)
                return self._send(500, json.dumps({"error": str(e)}))
            print(f"  + {path.parent.name}/{path.name} ({length / 1e6:.1f} MB)", flush=True)
            self._send(200, json.dumps({"saved": path.name, **col.stats()}))

    return H


def _lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packets are sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def serve(dest, port=8000, title="Send photos", key=None, max_mb=500, host="0.0.0.0"):
    key = key or secrets.token_urlsafe(9)
    col = _Collector(dest, key, title, max_mb)
    httpd = ThreadingHTTPServer((host, port), _handler(col))
    httpd.daemon_threads = True
    print(f"Collecting photos into {col.dest.resolve()}")
    print(f"  Same Wi-Fi:   http://{_lan_ip()}:{port}/?k={key}")
    print(f"  This computer: http://localhost:{port}/?k={key}")
    print("  Friends elsewhere: run a tunnel, e.g.  cloudflared tunnel --url "
          f"http://localhost:{port}   and send them  <tunnel-url>/?k={key}")
    print("Keep this window open while people upload; Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopped. {col.stats()['photos']} files in {col.dest}")
    finally:
        httpd.server_close()


_PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title><style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e1dc;--accent:#1f5fbf;
--ok:#2e7d32;--bad:#c62828}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--card:#202023;--ink:#ececee;
--muted:#a0a0a8;--line:#333338;--accent:#7fb0ff;--ok:#6fcf74;--bad:#ff6b6b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:560px;margin:0 auto;padding:28px 16px}h1{font-size:24px;margin:0 0 4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;
margin-top:16px}label{display:block;font-weight:600;margin-bottom:6px}
input[type=text]{width:100%;padding:12px;border:1px solid var(--line);border-radius:8px;
background:transparent;color:inherit;font:inherit}
.drop{border:2px dashed var(--line);border-radius:12px;padding:28px 12px;text-align:center;
cursor:pointer}.drop.on{border-color:var(--accent)}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:12px 18px;
font:inherit;font-weight:600;width:100%;margin-top:12px}
.bar{height:10px;background:var(--line);border-radius:5px;overflow:hidden;margin:12px 0 6px}
.bar div{height:100%;width:0;background:var(--accent);transition:width .2s}
.muted{color:var(--muted);font-size:14px}.ok{color:var(--ok)}.bad{color:var(--bad)}
</style></head><body><main>
<h1>{{TITLE}}</h1><div class="muted">Your photos go straight to the person making the
poster. Originals are best - no need to resize anything.</div>
<div class="card"><label for="who">Your name</label>
<input id="who" type="text" placeholder="So we know who sent what" autocomplete="name"></div>
<div class="card"><div class="drop" id="drop"><b>Tap to choose photos</b><br>
<span class="muted">or drag them here. Videos and .zip files work too.</span></div>
<input id="files" type="file" multiple hidden
 accept="image/*,video/*,.heic,.heif,.dng,.cr2,.cr3,.nef,.arw,.raf,.orf,.rw2,.zip">
<div class="bar"><div id="bar"></div></div><div id="status" class="muted">Nothing uploaded yet.</div>
<div id="errs" class="bad muted"></div></div>
<div class="card muted" id="total"></div>
<script>
const KEY="{{KEY}}",who=document.getElementById("who"),drop=document.getElementById("drop"),
input=document.getElementById("files"),bar=document.getElementById("bar"),
statusEl=document.getElementById("status"),errs=document.getElementById("errs"),
total=document.getElementById("total");
try{who.value=localStorage.getItem("who")||""}catch(e){}
who.addEventListener("change",()=>{try{localStorage.setItem("who",who.value)}catch(e){}});
drop.onclick=()=>input.click();
drop.ondragover=e=>{e.preventDefault();drop.classList.add("on")};
drop.ondragleave=()=>drop.classList.remove("on");
drop.ondrop=e=>{e.preventDefault();drop.classList.remove("on");send([...e.dataTransfer.files])};
input.onchange=()=>{send([...input.files]);input.value=""};
function showTotal(s){total.textContent=`So far: ${s.photos} files from ${s.people} people (${s.mb} MB).`}
fetch(`/stats?k=${KEY}`).then(r=>r.json()).then(showTotal).catch(()=>{});
function upload(file,onProgress){return new Promise((res,rej)=>{
 const x=new XMLHttpRequest(),name=encodeURIComponent(file.name),w=encodeURIComponent(who.value||"guest");
 x.open("POST",`/upload?k=${KEY}&name=${name}&who=${w}`);
 x.upload.onprogress=e=>onProgress(e.loaded);
 x.onload=()=>x.status==200?res(JSON.parse(x.responseText)):rej(new Error(x.responseText));
 x.onerror=()=>rej(new Error("network error"));x.send(file)})}
async function send(files){
 if(!files.length)return;
 if(!who.value.trim()){who.focus();statusEl.textContent="Add your name first, then choose the photos again.";return}
 const sizes=files.map(f=>f.size),all=sizes.reduce((a,b)=>a+b,0),loaded=new Array(files.length).fill(0);
 let done=0,failed=0,next=0;
 const tick=()=>{bar.style.width=(100*loaded.reduce((a,b)=>a+b,0)/Math.max(all,1))+"%";
  statusEl.textContent=`Uploading ${done+failed} of ${files.length}...`};
 async function worker(){while(next<files.length){const i=next++;
  for(let attempt=1;attempt<=3;attempt++){try{const s=await upload(files[i],b=>{loaded[i]=b;tick()});
    loaded[i]=sizes[i];done++;showTotal(s);break}
   catch(e){if(attempt==3){failed++;errs.textContent+=`${files[i].name} failed. `}}}
  tick()}}
 await Promise.all([worker(),worker(),worker()]);
 statusEl.innerHTML=failed?`<span class="bad">${done} sent, ${failed} failed - try those again.</span>`
  :`<span class="ok">All ${done} sent. Thank you!</span> You can add more.`}
</script></main></body></html>"""
