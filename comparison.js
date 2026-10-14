'use strict';
const $=id=>document.getElementById(id);
const fmt=x=>Math.abs(x)>0&&(Math.abs(x)<.001||Math.abs(x)>=1e4)?x.toExponential(3):Number(x).toPrecision(5);
function chart(id,x,series,{logX=false,logY=false,xLabel='k',yLabel='',band,zero=false,marker}={}){
 const canvas=$(id), rect=canvas.getBoundingClientRect(), ratio=window.devicePixelRatio||1;
 canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;
 const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
 const w=rect.width,h=rect.height,m={l:58,r:16,t:14,b:38};
 const tx=v=>logX?Math.log10(v):v,ty=v=>logY?Math.log10(v):v;
 const indices=x.map((v,i)=>i).filter(i=>Number.isFinite(x[i])&&(!logX||x[i]>0));
 let xmin=Math.min(...indices.map(i=>tx(x[i]))),xmax=Math.max(...indices.map(i=>tx(x[i])));
 const all=series.flatMap(s=>indices.map(i=>s.y[i])).filter(v=>Number.isFinite(v)&&(!logY||v>1e-18));
 if(!all.length){ctx.fillStyle=colors.gray;ctx.font='13px system-ui';ctx.fillText('No nonzero energy at this time',65,100);return;}
 let ymin=Math.min(...all.map(ty)),ymax=Math.max(...all.map(ty));
 if(zero){ymin=Math.min(ymin,0);ymax=Math.max(ymax,0);}
 if(ymax-ymin<1e-14){ymax+=.1;ymin-=.1;}const pad=(ymax-ymin)*.08;ymin-=pad;ymax+=pad;
 if(xmin===xmax)xmax=xmin+1;
 const px=v=>m.l+(tx(v)-xmin)/(xmax-xmin)*(w-m.l-m.r);
 const py=v=>h-m.b-(ty(v)-ymin)/(ymax-ymin)*(h-m.t-m.b);
 if(band){ctx.fillStyle='rgba(239,169,112,.09)';const a=Math.max(m.l,px(band[0])),b=Math.min(w-m.r,px(band[1]));ctx.fillRect(a,m.t,b-a,h-m.t-m.b);}
 ctx.font='10px system-ui';ctx.textBaseline='middle';
 for(let j=0;j<=4;j++){const yy=ymin+(ymax-ymin)*j/4,yyval=logY?10**yy:yy,Y=py(yyval);ctx.strokeStyle='#2a363d';ctx.beginPath();ctx.moveTo(m.l,Y);ctx.lineTo(w-m.r,Y);ctx.stroke();ctx.fillStyle='#9fadb4';ctx.textAlign='right';ctx.fillText(logY?yyval.toExponential(0):fmt(yyval),m.l-8,Y);}
 for(let j=0;j<=5;j++){const xx=xmin+(xmax-xmin)*j/5,v=logX?10**xx:xx;ctx.fillStyle='#9fadb4';ctx.textAlign='center';ctx.fillText(logX?v.toPrecision(2):Number(v.toFixed(1)),px(v),h-m.b+15);}
 if(zero){ctx.strokeStyle='#77888f';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(m.l,py(0));ctx.lineTo(w-m.r,py(0));ctx.stroke();ctx.setLineDash([]);}
 ctx.save();ctx.beginPath();ctx.rect(m.l,m.t,w-m.l-m.r,h-m.t-m.b);ctx.clip();
 for(const s of series){ctx.strokeStyle=s.color;ctx.lineWidth=s.dashed?1.2:2;ctx.setLineDash(s.dash||[]);ctx.beginPath();let pen=false;for(const i of indices){const v=s.y[i];if(!Number.isFinite(v)||(logY&&v<=1e-18)){pen=false;continue;}if(pen)ctx.lineTo(px(x[i]),py(v));else ctx.moveTo(px(x[i]),py(v));pen=true;}ctx.stroke();}ctx.setLineDash([]);
 if(marker!==undefined){ctx.strokeStyle=colors.orange;ctx.beginPath();ctx.moveTo(px(marker),m.t);ctx.lineTo(px(marker),h-m.b);ctx.stroke();}ctx.restore();
 ctx.fillStyle='#9fadb4';ctx.textAlign='center';ctx.fillText(xLabel,(w+m.l)/2,h-6);ctx.save();ctx.translate(12,h/2);ctx.rotate(-Math.PI/2);ctx.fillText(yLabel,0,0);ctx.restore();
 return {ctx,px,m,w,h,indices};
}

const palette=['#73d6cf','#efa970','#7ab8f5','#ed91bd','#e4d46e','#b9a2f7','#92ce83','#fa8e70'];
let runs=[], enabled=new Set(), plots={};
function drawPlot(id,x,key,options,history=false){
 const active=runs.filter(r=>enabled.has(r.id));
 const canvas=$(id);
 if(!active.length){const rect=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#9fadb4';ctx.font='13px system-ui';ctx.fillText('Select a run above to display results.',25,50);delete plots[id];return;}
 const series=active.map(r=>({y:history?r.samples.map(s=>s[key]):r.average[key],color:r.color,dash:r.dash,run:r}));
 const geometry=chart(id,x,series,options);
 plots[id]={...geometry,x,series,options,redraw:()=>drawPlot(id,x,key,options,history)};
}
function render(){
 if(!runs.length)return;
 const first=runs[0],c=first.config,band=[c.kf-c.bandwidth/2,c.kf+c.bandwidth/2];
 drawPlot('compare-spectrum',first.k,'spectrum',{logX:true,logY:true,xLabel:'k',yLabel:'E(k)',band});
 drawPlot('compare-energy-flux',first.flux_k,'energy_flux',{xLabel:'K',yLabel:'ΠE(K)',zero:true,band});
 drawPlot('compare-enstrophy-flux',first.flux_k,'enstrophy_flux',{xLabel:'K',yLabel:'ΠZ(K)',zero:true,band});
 const key=$('compare-history-kind').value;
 drawPlot('compare-history',first.samples.map(s=>s.t),key,{xLabel:'Time t',yLabel:key==='energy'?'E total':'Z total',band:[600,800]},true);
 $('plot-tooltip').hidden=true;
}
function inspectPlot(id,event){
 let plot=plots[id];if(!plot)return;
 plot.redraw();plot=plots[id];
 const rect=$(id).getBoundingClientRect(),mouse=event.clientX-rect.left;
 if(mouse<plot.m.l||mouse>plot.w-plot.m.r){$('plot-tooltip').hidden=true;return;}
 const index=plot.indices.reduce((best,i)=>Math.abs(plot.px(plot.x[i])-mouse)<Math.abs(plot.px(plot.x[best])-mouse)?i:best,plot.indices[0]);
 const ctx=plot.ctx;ctx.strokeStyle='#9fadb4';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(plot.px(plot.x[index]),plot.m.t);ctx.lineTo(plot.px(plot.x[index]),plot.h-plot.m.b);ctx.stroke();ctx.setLineDash([]);
 const tooltip=$('plot-tooltip');tooltip.replaceChildren();const title=document.createElement('strong');title.textContent=`${plot.options.xLabel} = ${fmt(plot.x[index])}`;tooltip.append(title);
 plot.series.forEach(s=>{const row=document.createElement('div');row.className='tooltip-row';const label=document.createElement('span');label.style.color=s.color;label.textContent=`α=${s.run.config.alpha.toFixed(3)}`;const value=document.createElement('span');value.textContent=fmt(s.y[index]);row.append(label,value);tooltip.append(row);});
 tooltip.hidden=false;const size=tooltip.getBoundingClientRect();tooltip.style.left=Math.max(8,Math.min(innerWidth-size.width-8,event.clientX+16))+'px';tooltip.style.top=Math.max(8,Math.min(innerHeight-size.height-8,event.clientY+16))+'px';
}
function validate(comparison){
 if(comparison.missing?.length||comparison.runs.length!==8)throw new Error('The comparison needs all eight saved runs.');
 const expected=['0.008','0.009','0.010','0.011','0.012','0.013','0.014','0.015'];
 const sorted=[...comparison.runs].sort((a,b)=>a.config.alpha-b.config.alpha);
 const reference=sorted[0];
 sorted.forEach((r,i)=>{
  if(r.config.alpha.toFixed(3)!==expected[i]||r.config.alpha_right!=null||r.config.duration!==800||Math.abs(r.summary.average_start-600)>1e-6||Math.abs(r.summary.average_end-800)>1e-6)throw new Error('Unexpected drag or averaging interval in comparison.');
  for(const key of ['n','length','nu','epsilon','kf','bandwidth','dt','seed'])if(r.config[key]!==reference.config[key])throw new Error('The experiments use different physical parameters.');
  for(const key of ['k','flux_k'])if(r[key].length!==reference[key].length||r[key].some((v,j)=>Math.abs(v-reference[key][j])>1e-9))throw new Error('Incompatible wavenumber grids.');
  if(r.samples.length!==reference.samples.length||r.samples.some((s,j)=>Math.abs(s.t-reference.samples[j].t)>1e-8))throw new Error('Incompatible history sample times.');
  for(const key of ['spectrum','energy_flux','enstrophy_flux'])if(r.average[key].length!==r.k.length||r.average[key].some(v=>!Number.isFinite(v)))throw new Error('Incomplete averaged diagnostics.');
 });
 return sorted;
}
async function boot(){
 try{
  const response=await fetch('comparison-data.json',{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);
  runs=validate(await response.json());
  runs.forEach((r,i)=>{
   r.color=palette[i];r.dash=i<4?[]:[5,3];enabled.add(r.id);
   const label=document.createElement('label');label.className='run-key';const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=true;checkbox.setAttribute('aria-label',r.name);
   checkbox.addEventListener('change',()=>{if(checkbox.checked)enabled.add(r.id);else enabled.delete(r.id);render();});
   const swatch=document.createElement('span');swatch.className='run-swatch';swatch.style.background=r.color;
   const text=document.createElement('span');text.textContent=`Run ${i+1} · α=${r.config.alpha.toFixed(3)}`;label.append(checkbox,swatch,text);$('run-legend').append(label);
   const row=document.createElement('tr');const cell=document.createElement('td');const link=document.createElement('a');link.href=`index.html?run=${encodeURIComponent(r.id)}`;link.textContent=r.name;cell.append(link);row.append(cell);
   [r.config.alpha.toFixed(3),fmt(r.average.energy),fmt(r.average.enstrophy),fmt(r.summary.inverse_range_mean_flux)].forEach(value=>{const td=document.createElement('td');td.textContent=value;row.append(td);});$('comparison-table').append(row);
  });
  $('show-all').disabled=false;$('comparison-status').textContent='All eight archived runs loaded · uniform drag · averaged t = 600–800';
  $('show-all').addEventListener('click',()=>{runs.forEach(r=>enabled.add(r.id));document.querySelectorAll('#run-legend input').forEach(input=>input.checked=true);render();});
  $('compare-history-kind').addEventListener('change',render);window.addEventListener('resize',render);
  for(const id of ['compare-spectrum','compare-energy-flux','compare-enstrophy-flux','compare-history']){
   $(id).addEventListener('pointermove',event=>inspectPlot(id,event));$(id).addEventListener('pointerdown',event=>inspectPlot(id,event));$(id).addEventListener('pointerleave',()=>{if(plots[id])plots[id].redraw();$('plot-tooltip').hidden=true;});
  }
  render();
 }catch(error){$('comparison-status').textContent=`Comparison could not load: ${error.message}`;$('comparison-status').style.color='#efa970';}
}
boot();
