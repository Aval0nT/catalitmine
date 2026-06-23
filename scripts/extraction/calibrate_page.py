"""calibrate_page.py — the semantic layer: pixel traces → real values + names.

Generates a self-contained, offline HTML page (open with file://, no server)
that turns a geometry model's PIXEL traces (.lfline.json from the lineformer
backend, or any {panels:[{series:[{points:[{x,y}]}]}]} in image pixels) into
DATA. The human:

  1. clicks two ticks on each axis and types their values  → pixel↔value
     calibration (linear or log per axis);
  2. types the axis labels/units and the per-series catalyst names
     (the legend = catalyst identity, the DB join key);
  3. checks the live value-space re-plot against the original;
  4. accepts → exports a calibrated JSON.

This IS the human gate: only what the human accepts is exported. Every accepted
figure is also training-grade ground truth (pixel traces + calibrated values).

Geometry models never do this step — they only ever return pixels. This closes
the gap between "traces extracted" and "data in the database".

  venv/bin/python scripts/extraction/calibrate_page.py \
    --image figures/_calib_test/mcat_fig06_panelA.png \
    --lfline outputs/charts/mcat_fig06_panelA.lfline.json
  → outputs/reports/calibrate_<stem>.html  (open it, calibrate, Export)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# distinct trace colours (must match the JS PALETTE below)
PALETTE = ["#e6194B", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
           "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990"]

_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<title>Calibrate — {stem}</title>
<style>
  body{{font:13px/1.45 -apple-system,Segoe UI,sans-serif;margin:0;background:#1a1a1a;color:#ddd}}
  #wrap{{display:flex;gap:14px;padding:14px;align-items:flex-start}}
  #left{{flex:0 0 auto}} #right{{flex:1;min-width:320px;max-width:460px}}
  canvas{{border:1px solid #444;cursor:crosshair;background:#000}}
  h2{{margin:.2em 0;font-size:15px;color:#fff}} h3{{margin:.8em 0 .3em;color:#9cf;font-size:13px}}
  .row{{display:flex;gap:6px;align-items:center;margin:4px 0}}
  .row label{{flex:0 0 86px;color:#aaa}}
  input[type=text],input[type=number]{{background:#2a2a2a;border:1px solid #555;color:#eee;border-radius:4px;padding:4px 6px;width:90px}}
  input.wide{{width:150px}}
  button{{background:#2d6cdf;color:#fff;border:0;border-radius:5px;padding:6px 10px;cursor:pointer;font-size:12px}}
  button.set{{background:#444}} button.set.armed{{background:#d68a00}} button.set.done{{background:#2a7d2a}}
  button.ghost{{background:#3a3a3a}}
  #status{{padding:6px 8px;border-radius:5px;background:#222;margin:6px 0;min-height:18px}}
  .swatch{{width:12px;height:12px;border-radius:2px;display:inline-block;margin-right:6px;vertical-align:middle}}
  #replot{{border:1px solid #444;background:#fff;margin-top:6px}}
  textarea{{width:100%;height:120px;background:#111;color:#9f9;border:1px solid #444;font:11px monospace}}
  .hint{{color:#888;font-size:11px}} .ok{{color:#6c6}} .warn{{color:#e88}}
  .axwrap{{border:1px solid #383838;border-radius:6px;padding:8px;margin:6px 0}}
</style></head><body>
<div id="wrap">
  <div id="left">
    <canvas id="cv"></canvas>
    <div class="hint">Click the image to place the armed tick. Hover shows live (x,y) once calibrated.</div>
    <h3>Value-space re-plot (sanity check)</h3>
    <canvas id="replot" width="380" height="260"></canvas>
  </div>
  <div id="right">
    <h2>{stem}</h2>
    <div class="hint">{doi} · {nseries} series · {npts} pts</div>
    <div id="status">Set 2 ticks on each axis, then name the series.</div>

    <div class="axwrap">
      <h3>X axis</h3>
      <div class="row"><label>Label</label><input id="xlabel" class="wide" type="text" placeholder="e.g. Time on stream"><input id="xunit" type="text" placeholder="unit" style="width:60px"></div>
      <div class="row"><button class="set" id="bx1">Set X-tick A</button><input id="xv1" type="number" placeholder="value"></div>
      <div class="row"><button class="set" id="bx2">Set X-tick B</button><input id="xv2" type="number" placeholder="value"></div>
      <div class="row"><label>Log scale</label><input id="xlog" type="checkbox"></div>
    </div>
    <div class="axwrap">
      <h3>Y axis</h3>
      <div class="row"><label>Label</label><input id="ylabel" class="wide" type="text" placeholder="e.g. MeOH conversion"><input id="yunit" type="text" placeholder="unit" style="width:60px"></div>
      <div class="row"><button class="set" id="by1">Set Y-tick A</button><input id="yv1" type="number" placeholder="value"></div>
      <div class="row"><button class="set" id="by2">Set Y-tick B</button><input id="yv2" type="number" placeholder="value"></div>
      <div class="row"><label>Log scale</label><input id="ylog" type="checkbox"></div>
    </div>

    <h3>Series → catalyst name</h3>
    <div id="names"></div>

    <div class="row" style="margin-top:10px">
      <button id="accept">✓ Accept &amp; Export</button>
      <button class="ghost" id="reject">✗ Reject figure</button>
      <button class="ghost" id="redraw">redraw</button>
    </div>
    <div class="hint">Export downloads the calibrated JSON and also fills the box below (copy if download is blocked).</div>
    <textarea id="out" placeholder="calibrated JSON appears here on Accept"></textarea>
  </div>
</div>
<script>
const IMG_SRC="{img_b64}";
const SERIES={series_json};
const META={{stem:"{stem}",doi:"{doi}",image:"{image_name}"}};
const PALETTE={palette_json};

const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const rp=document.getElementById('replot'), rctx=rp.getContext('2d');
const img=new Image();
let ticks={{x1:null,x2:null,y1:null,y2:null}};   // each {{px,py}}
let arm=null;

img.onload=()=>{{ cv.width=img.naturalWidth; cv.height=img.naturalHeight;
  // cap display width for big images, keep aspect (CSS only; canvas stays native px)
  const maxw=560; if(img.naturalWidth>maxw){{cv.style.width=maxw+'px';cv.style.height=(img.naturalHeight*maxw/img.naturalWidth)+'px';}}
  draw(); }};
img.src=IMG_SRC;

function draw(){{
  ctx.drawImage(img,0,0);
  SERIES.forEach((s,i)=>{{ ctx.strokeStyle=PALETTE[i%PALETTE.length]; ctx.lineWidth=2; ctx.beginPath();
    s.points.forEach((p,j)=> j?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y)); ctx.stroke(); }});
  for(const k in ticks){{ const t=ticks[k]; if(!t)continue;
    ctx.strokeStyle='#ff0'; ctx.lineWidth=1;
    if(k[0]==='x'){{ctx.beginPath();ctx.moveTo(t.px,0);ctx.lineTo(t.px,cv.height);ctx.stroke();}}
    else{{ctx.beginPath();ctx.moveTo(0,t.py);ctx.lineTo(cv.width,t.py);ctx.stroke();}}
    ctx.fillStyle='#ff0'; ctx.fillText(k,t.px+3,t.py-3); }}
}}

function evToPix(e){{ const r=cv.getBoundingClientRect();
  return {{px:(e.clientX-r.left)*cv.width/r.width, py:(e.clientY-r.top)*cv.height/r.height}}; }}

cv.addEventListener('click',e=>{{ if(!arm)return; const p=evToPix(e); ticks[arm]=p;
  document.getElementById('b'+arm).classList.remove('armed'); document.getElementById('b'+arm).classList.add('done');
  arm=null; draw(); status(); }});

cv.addEventListener('mousemove',e=>{{ const cal=calib(); if(!cal)return; const p=evToPix(e);
  status('@ '+fmt(cal.fx(p.px))+', '+fmt(cal.fy(p.py))); }});

['x1','x2','y1','y2'].forEach(k=>{{ document.getElementById('b'+k).onclick=()=>{{
  ['x1','x2','y1','y2'].forEach(o=>document.getElementById('b'+o).classList.remove('armed'));
  arm=k; document.getElementById('b'+k).classList.add('armed'); status('Click the image to place '+k.toUpperCase()); }}; }});

function num(id){{const v=parseFloat(document.getElementById(id).value);return isNaN(v)?null:v;}}
function lg(id){{return document.getElementById(id).checked;}}

function axisMap(p1,v1,p2,v2,log){{ if(p1==null||p2==null||v1==null||v2==null||p1===p2)return null;
  if(log){{ if(v1<=0||v2<=0)return null; const l1=Math.log10(v1),l2=Math.log10(v2);
    return p=>Math.pow(10, l1+(p-p1)*(l2-l1)/(p2-p1)); }}
  return p=> v1+(p-p1)*(v2-v1)/(p2-p1); }}

function calib(){{ if(!(ticks.x1&&ticks.x2&&ticks.y1&&ticks.y2))return null;
  const fx=axisMap(ticks.x1.px,num('xv1'),ticks.x2.px,num('xv2'),lg('xlog'));
  const fy=axisMap(ticks.y1.py,num('yv1'),ticks.y2.py,num('yv2'),lg('ylog'));
  return (fx&&fy)?{{fx,fy}}:null; }}

function fmt(v){{ return (Math.abs(v)>=100||v===0)?v.toFixed(0):v.toFixed(2); }}
function status(m){{ const el=document.getElementById('status');
  if(m){{el.textContent=m;return;}}
  const c=calib(); el.innerHTML = c? '<span class=ok>calibrated ✓ — hover to read values, then Accept</span>'
    : 'ticks set: '+['x1','x2','y1','y2'].filter(k=>ticks[k]).length+'/4 · values needed too'; replot(); }}

function buildNames(){{ const d=document.getElementById('names'); d.innerHTML='';
  SERIES.forEach((s,i)=>{{ const row=document.createElement('div'); row.className='row';
    row.innerHTML='<span class=swatch style="background:'+PALETTE[i%PALETTE.length]+'"></span>'+
      '<input type=text class="wide nm" data-i="'+i+'" value="'+(s.name||('line_'+(i+1)))+'">'+
      '<label style="flex:0 0 auto"><input type=checkbox class=keep data-i="'+i+'" checked> keep</label>';
    d.appendChild(row); }}); }}

function replot(){{ rctx.fillStyle='#fff'; rctx.fillRect(0,0,rp.width,rp.height); const c=calib(); if(!c)return;
  // value-space bounds
  let xs=[],ys=[]; SERIES.forEach(s=>s.points.forEach(p=>{{xs.push(c.fx(p.x));ys.push(c.fy(p.y));}}));
  const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
  const PADl=44,PADb=26,W=rp.width-PADl-8,H=rp.height-PADb-8;
  const sx=v=>PADl+(v-xmin)/((xmax-xmin)||1)*W, sy=v=>8+H-(v-ymin)/((ymax-ymin)||1)*H;
  rctx.strokeStyle='#999'; rctx.strokeRect(PADl,8,W,H);
  rctx.fillStyle='#333'; rctx.font='10px sans-serif';
  rctx.fillText(fmt(ymax),2,14); rctx.fillText(fmt(ymin),2,8+H); rctx.fillText(fmt(xmin),PADl,rp.height-12); rctx.fillText(fmt(xmax),rp.width-30,rp.height-12);
  SERIES.forEach((s,i)=>{{ rctx.strokeStyle=PALETTE[i%PALETTE.length]; rctx.lineWidth=1.5; rctx.beginPath();
    s.points.forEach((p,j)=>{{const X=sx(c.fx(p.x)),Y=sy(c.fy(p.y)); j?rctx.lineTo(X,Y):rctx.moveTo(X,Y);}}); rctx.stroke(); }}); }}

function exportJSON(accepted){{ const c=calib();
  if(accepted&&!c){{alert('Finish calibration first: 2 ticks + values on each axis.');return;}}
  const names=[...document.querySelectorAll('.nm')], keeps=[...document.querySelectorAll('.keep')];
  const series=SERIES.map((s,i)=>({{ name:names[i].value.trim(), keep:keeps[i].checked,
    points: accepted? s.points.map(p=>({{x:+c.fx(p.x).toFixed(4),y:+c.fy(p.y).toFixed(4)}})) : s.points }}))
    .filter(s=>s.keep).map(({{keep,...r}})=>r);
  const obj={{ image:META.image, doi:META.doi, status:accepted?'accepted':'rejected',
    x_axis:{{label:document.getElementById('xlabel').value,unit:document.getElementById('xunit').value,log:lg('xlog')}},
    y_axis:{{label:document.getElementById('ylabel').value,unit:document.getElementById('yunit').value,log:lg('ylog')}},
    calibration: c? {{x:[ticks.x1.px,num('xv1'),ticks.x2.px,num('xv2')],y:[ticks.y1.py,num('yv1'),ticks.y2.py,num('yv2')]}} : null,
    series }};
  const txt=JSON.stringify(obj,null,2); document.getElementById('out').value=txt;
  if(location.protocol.startsWith('http')){{           // served by calibrate_server → save into the project
    fetch('/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:txt}})
      .then(r=>r.json()).then(j=>{{ status(j.ok? ('✓ saved to project → '+j.path) : ('save failed: '+j.error));
        if(j.ok&&j.next){{setTimeout(()=>location.href=j.next,600);}} }})   // auto-advance if a worklist is active
      .catch(e=>{{ status('save endpoint unreachable, downloaded instead'); download(txt); }});
  }} else {{ download(txt); }}                          // opened via file:// → browser download (fallback)
}}
function download(txt){{ const blob=new Blob([txt],{{type:'application/json'}}); const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download='calibrated_'+META.stem+'.json'; a.click(); }}
document.getElementById('accept').onclick=()=>exportJSON(true);
document.getElementById('reject').onclick=()=>exportJSON(false);
document.getElementById('redraw').onclick=()=>{{draw();status();}};
['xv1','xv2','yv1','yv2','xlog','ylog'].forEach(id=>document.getElementById(id).addEventListener('input',()=>status()));
buildNames();
</script></body></html>"""


def build_html(image_path: Path, lfline_path: Path, panel: int = 0) -> tuple[str, str, int, int]:
    """Return (html, stem, n_series, n_points) for a figure + its pixel traces.
    Shared by the CLI (writes a file://-openable page) and calibrate_server.py
    (serves it over http so Accept saves into the project)."""
    image_path, lfline_path = Path(image_path), Path(lfline_path)
    data = json.loads(lfline_path.read_text())
    pn = data["panels"][panel]
    series = [{"name": s.get("name", f"line_{i+1}"), "points": s["points"]}
              for i, s in enumerate(pn["series"])]
    npts = sum(len(s["points"]) for s in series)
    media = mimetypes.guess_type(str(image_path))[0] or "image/png"
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode()
    stem = image_path.stem
    html = _HTML.format(
        stem=stem, doi=data.get("image", ""), image_name=image_path.name,
        nseries=len(series), npts=npts,
        img_b64=f"data:{media};base64,{b64}",
        series_json=json.dumps(series),
        palette_json=json.dumps(PALETTE),
    )
    return html, stem, len(series), npts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--lfline", required=True, help=".lfline.json (or any {panels:[{series:[{points}]}]})")
    ap.add_argument("--panel", type=int, default=0, help="which panel (default 0)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    html, stem, nser, npts = build_html(Path(args.image), Path(args.lfline), args.panel)
    out = Path(args.out) if args.out else ROOT / "outputs" / "reports" / f"calibrate_{stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({nser} series, {npts} pts)")
    print(f"open it:  open {out}")
    print("note: opened via file:// this downloads on Accept; for save-to-project use calibrate_server.py")


if __name__ == "__main__":
    main()
