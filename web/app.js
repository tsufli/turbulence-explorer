'use strict';
let data, frameIndex=0, timer, playing=false, renderToken=0, playEpoch=0;
let resultBase=new URL('.',location.href);
const frameCache=new Map(), pendingFrames=new Map();
const $=id=>document.getElementById(id);
const colors={cyan:'#73d6cf',orange:'#efa970',gray:'#7b8c94'};
const fmt=x=>Math.abs(x)>0 && (Math.abs(x)<.001||Math.abs(x)>=1e4)?x.toExponential(2):Number(x).toPrecision(4);
function nearest(samples,t){return samples.reduce((a,b)=>Math.abs(b.t-t)<Math.abs(a.t-t)?b:a);}
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
 for(const s of series){ctx.strokeStyle=s.color;ctx.lineWidth=s.dashed?1.2:2;ctx.setLineDash(s.dashed?[5,4]:[]);ctx.beginPath();let pen=false;for(const i of indices){const v=s.y[i];if(!Number.isFinite(v)||(logY&&v<=1e-18)){pen=false;continue;}if(pen)ctx.lineTo(px(x[i]),py(v));else ctx.moveTo(px(x[i]),py(v));pen=true;}ctx.stroke();}ctx.setLineDash([]);
 if(marker!==undefined){ctx.strokeStyle=colors.orange;ctx.beginPath();ctx.moveTo(px(marker),m.t);ctx.lineTo(px(marker),h-m.b);ctx.stroke();}ctx.restore();
 ctx.fillStyle='#9fadb4';ctx.textAlign='center';ctx.fillText(xLabel,(w+m.l)/2,h-6);ctx.save();ctx.translate(12,h/2);ctx.rotate(-Math.PI/2);ctx.fillText(yLabel,0,0);ctx.restore();
}
async function getFrame(index){
 if(frameCache.has(index))return frameCache.get(index);
 if(pendingFrames.has(index))return pendingFrames.get(index);
 const request=(async()=>{const meta=data.frames[index],response=await fetch(new URL(meta.url,resultBase).href+'?run='+encodeURIComponent(data.generated_at),{cache:'no-store'});if(!response.ok)throw new Error(`Frame HTTP ${response.status}`);const buffer=await response.arrayBuffer(),count=meta.n**2;if(buffer.byteLength!==count*12)throw new Error('Unexpected frame size');const planes=new Float32Array(buffer),frame={...meta,values:planes.subarray(0,count),u:planes.subarray(count,2*count),v:planes.subarray(2*count)};frameCache.set(index,frame);while(frameCache.size>12)frameCache.delete(frameCache.keys().next().value);return frame;})();
 pendingFrames.set(index,request);try{return await request;}finally{pendingFrames.delete(index);}
}
function drawField(frame){const a=frame.values,n=frame.n,c=$('vorticity'),ctx=c.getContext('2d'),im=ctx.createImageData(n,n),limit=data.colorLimit;for(let y=0;y<n;y++)for(let x=0;x<n;x++){const v=Math.max(-1,Math.min(1,a[y*n+x]/limit)),base=[24,33,38],end=v>0?[225,118,100]:[63,133,203],p=((n-1-y)*n+x)*4;for(let j=0;j<3;j++)im.data[p+j]=base[j]+Math.abs(v)*(end[j]-base[j]);im.data[p+3]=255;}const off=document.createElement('canvas');off.width=off.height=n;off.getContext('2d').putImageData(im,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(off,0,0,c.width,c.height);if(data.config.alpha_right!=null){ctx.save();ctx.strokeStyle='#e7edef';ctx.setLineDash([6,6]);ctx.lineWidth=1.5;ctx.beginPath();for(const x of [1,c.width/2,c.width-1]){ctx.moveTo(x,0);ctx.lineTo(x,c.height);}ctx.stroke();ctx.restore();}}
async function renderSpatial(index){
 const token=++renderToken,meta=data.frames[index];
 $('vorticity').setAttribute('aria-busy','true');
 $('field-time').textContent=`Loading t = ${meta.t.toFixed(2)}…`;
 try{const frame=await getFrame(index);if(token!==renderToken)return;drawField(frame);$('field-time').textContent=`t = ${frame.t.toFixed(2)}`;$('vorticity').setAttribute('aria-busy','false');if(playing&&index+1<data.frames.length)getFrame(index+1).catch(()=>{});}
 catch(error){if(token!==renderToken)return;stopPlayback();$('field-time').textContent=error.message;}
}
function render(){if(!data)return;const frame=data.frames[frameIndex],sample=nearest(data.samples,frame.t),s=$('view').value==='average'?data.average:sample;
 $('time-label').textContent=frame.t.toFixed(2);$('energy').textContent=fmt(sample.energy);const spatial=renderSpatial(frameIndex);
 const len=data.k.filter(k=>k<=data.complete_shell_max).length,k=data.k.slice(0,len),K=data.flux_k.slice(0,len),band=[data.config.kf-data.config.bandwidth/2,data.config.kf+data.config.bandwidth/2];
 const anchor=nearest(k.map((v,i)=>({t:v,i})),data.config.kf).i,level=s.spectrum[anchor]||1e-10;
 const guide=(exp,side)=>k.map(v=>v>0&&(side==='left'?v<band[0]:v>band[1])?level*(v/data.config.kf)**exp:null);
 chart('spectrum',k,[{y:s.spectrum,color:colors.cyan},{y:guide(-5/3,'left'),color:colors.gray,dashed:true},{y:guide(-3,'right'),color:colors.gray,dashed:true}],{logX:true,logY:true,yLabel:'E(k)',band});
 chart('energy-flux',K,[{y:s.energy_flux,color:colors.cyan}],{yLabel:'ΠE(K)',xLabel:'K',zero:true,band});
 chart('enstrophy-flux',K,[{y:s.enstrophy_flux,color:colors.orange}],{yLabel:'ΠZ(K)',xLabel:'K',zero:true,band});
 const kind=$('history-kind').value;chart('history',data.samples.map(v=>v.t),[{y:data.samples.map(v=>v[kind]),color:colors.cyan}],{xLabel:'Time t',yLabel:kind==='energy'?'E total':'Z total',band:[data.summary.average_start,data.summary.average_end],marker:frame.t});return spatial;
}
async function boot(){try{
 const archiveResponse=await fetch('archive.json',{cache:'no-store'});
 if(archiveResponse.ok){
  const archive=await archiveResponse.json(),runs=archive.runs;
  if(!runs.length)throw new Error('Archive is empty');
  const requested=new URL(location.href).searchParams.get('run');
  const selected=requested?runs.find(r=>r.id===requested):runs[0];
  if(!selected)throw new Error('Experiment not found in archive');
  const picker=$('experiment');picker.replaceChildren();
  runs.forEach(r=>{const option=document.createElement('option');option.value=r.id;option.textContent=`${r.name?r.name+' · ':''}${new Date(r.generated_at).toLocaleDateString()} · ${r.config.n}² · ${r.config.alpha_right==null?`α=${r.config.alpha}`:`α L/R=${r.config.alpha}/${r.config.alpha_right}`} · T=${r.config.duration} · seed=${r.config.seed} · #${r.id}`;picker.appendChild(option);});
  picker.value=selected.id;picker.disabled=false;
  picker.addEventListener('change',()=>{const url=new URL(location.href);url.searchParams.set('run',picker.value);location.assign(url.href);});
  resultBase=new URL(`runs/${selected.id}/`,location.href);
  $('experiment-run').href=selected.run_url;$('experiment-run').hidden=false;
 }else if(archiveResponse.status!==404){throw new Error(`Archive HTTP ${archiveResponse.status}`);}
 const response=await fetch(new URL('results.json?schema=2',resultBase),{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);data=await response.json();if(data.schema_version!==2||!data.frames.length)throw new Error('Unsupported or empty results; refresh after deployment');
 data.colorLimit=Math.max(1e-12,...data.frames.map(f=>f.vorticity_max));$('field-resolution').textContent=`Full ${data.config.n} × ${data.config.n} simulation grid`;
 $('drag-layout').textContent=data.config.alpha_right==null?'':`Left half: α=${data.config.alpha} · Right half: α=${data.config.alpha_right}. Periodic interfaces at x=0 and x=L/2.`;
 $('equation-drag').textContent=data.config.alpha_right==null?'αω':'curl[α(x)u]';
 $('color-min').textContent='−'+fmt(data.colorLimit);$('color-max').textContent='+'+fmt(data.colorLimit);
 $('grid').textContent=`${data.config.n} × ${data.config.n}`;$('forcing').textContent=`kf = ${data.config.kf}`;$('flux').textContent=data.summary.inverse_range_mean_flux===null?'N/A':fmt(data.summary.inverse_range_mean_flux);
 $('time').max=data.frames.length-1;$('time').disabled=false;$('play').disabled=false;frameIndex=data.frames.length-1;$('time').value=frameIndex;
 $('status').textContent=`${data.experiment_name||'Computed run'} · averaged t = ${data.summary.average_start.toFixed(1)}–${data.summary.average_end.toFixed(1)} · stationarity not certified`;
 const labels={n:'Grid N',length:'Box side L',nu:'Viscosity ν',alpha:data.config.alpha_right==null?'Linear drag α':'Left-half drag α',alpha_right:'Right-half drag α',epsilon:'Mean injection ε',kf:'Forcing wavenumber kf',bandwidth:'Full forcing bandwidth',dt:'Maximum timestep',duration:'Simulation time',average_after:'Average starts at',sample_interval:'Diagnostic interval',frame_interval:'Frame interval',seed:'Random seed'};
 const tbody=$('parameters').querySelector('tbody');Object.entries(data.config).forEach(([key,val])=>{const row=document.createElement('tr');for(const text of [labels[key]||key,val===null?'—':typeof val==='number'?fmt(val):val]){const cell=document.createElement('td');cell.textContent=text;row.appendChild(cell);}tbody.appendChild(row);});
 const checks=[['Maximum advective CFL',data.summary.max_cfl],['Energy budget residual',data.summary.energy_budget_residual],['Enstrophy budget residual',data.summary.enstrophy_budget_residual],['Max |Σ nonlinear energy transfer|',Math.max(...data.samples.map(s=>Math.abs(s.transfer_energy_sum)))],['Max |Σ nonlinear enstrophy transfer|',Math.max(...data.samples.map(s=>Math.abs(s.transfer_enstrophy_sum)))]];
 checks.forEach(([label,value])=>{const p=document.createElement('p');p.textContent=label+': ';const strong=document.createElement('strong');strong.textContent=fmt(value);p.appendChild(strong);$('checks').appendChild(p);});
 $('timestamp').textContent='Run generated '+new Date(data.generated_at).toLocaleString();render();
 }catch(error){$('status').textContent=`Results could not load: ${error.message}. Complete the GitHub Actions run, then refresh.`;$('status').style.color='#efa970';}}
function stopPlayback(){playing=false;playEpoch++;clearTimeout(timer);timer=null;$('play').textContent='▶ Play';}
async function advance(epoch){if(!playing||epoch!==playEpoch)return;await render();if(!playing||epoch!==playEpoch)return;timer=setTimeout(()=>{frameIndex=(frameIndex+1)%data.frames.length;$('time').value=frameIndex;advance(epoch);},130);}
$('time').addEventListener('input',()=>{stopPlayback();frameIndex=Number($('time').value);render();});$('view').addEventListener('change',render);$('history-kind').addEventListener('change',render);window.addEventListener('resize',render);
$('play').addEventListener('click',()=>{if(playing){stopPlayback();}else{playing=true;playEpoch++;if(frameIndex===data.frames.length-1)frameIndex=0;$('time').value=frameIndex;$('play').textContent='Ⅱ Pause';advance(playEpoch);}});
boot();
