'use strict';
// Geometric streamlines of a frozen velocity field, not time-evolving tracers.
const Streamlines = (() => {
 function wrap(x,n){return ((x%n)+n)%n;}
 function velocity(frame,x,y){
  const n=frame.n,X=wrap(x,n),Y=wrap(y,n),i=Math.floor(X),j=Math.floor(Y),a=X-i,b=Y-j;
  const ids=[j*n+i,j*n+(i+1)%n,((j+1)%n)*n+i,((j+1)%n)*n+(i+1)%n];
  const weights=[(1-a)*(1-b),a*(1-b),(1-a)*b,a*b];
  return [frame.u,frame.v].map(field=>ids.reduce((sum,id,k)=>sum+weights[k]*field[id],0));
 }
 function paths(frame){
  if(frame.speed_max===0)return [];
  const n=frame.n,cells=36,occupied=new Set(),result=[];
  const cell=(x,y)=>Math.floor(wrap(y,n)/n*cells)*cells+Math.floor(wrap(x,n)/n*cells);
  const unit=(x,y)=>{const [u,v]=velocity(frame,x,y),s=Math.hypot(u,v);return s>frame.speed_max*1e-4?[u/s,v/s]:null;};
  function trace(seed,sign){
   let [x,y]=seed,last=cell(x,y);const visited=new Set([last]),points=[seed],h=.65;
   for(let i=0;i<4*n;i++){
    const a=unit(x,y);if(!a)break;
    const b=unit(x+sign*h*a[0]/2,y+sign*h*a[1]/2);if(!b)break;
    const X=wrap(x+sign*h*b[0],n),Y=wrap(y+sign*h*b[1],n),key=cell(X,Y);
    if(key!==last){if(occupied.has(key)||visited.has(key))break;visited.add(key);last=key;}
    points.push([X,Y]);x=X;y=Y;
   }
   return points;
  }
  // Deterministic spatially spread seeds. Occupancy prevents an unreadable mesh.
  const seeds=[];for(let j=0;j<20;j++)for(let i=0;i<20;i++)seeds.push([(i+.37)*n/20,(j+.53)*n/20]);
  for(let k=0;k<seeds.length;k++){
   const seed=seeds[(k*137)%seeds.length];if(occupied.has(cell(...seed)))continue;
   const back=trace(seed,-1),forward=trace(seed,1),line=back.reverse().concat(forward.slice(1));
   if(line.length<8)continue;
   for(const p of line)occupied.add(cell(...p));result.push(line);
  }
  return result;
 }
 function draw(canvas,frame){
  const size=Math.max(1,canvas.getBoundingClientRect().width),ratio=window.devicePixelRatio||1;
  canvas.width=canvas.height=Math.round(size*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  ctx.fillStyle='#10191d';ctx.fillRect(0,0,size,size);
  if(!frame.speed_max){ctx.fillStyle='#9fadb4';ctx.font='13px system-ui';ctx.textAlign='center';ctx.fillText('Velocity is zero at this time',size/2,size/2);return;}
  const n=frame.n,scale=size/n,lines=paths(frame);ctx.strokeStyle='#73d6cf';ctx.lineWidth=.95;ctx.fillStyle='#efa970';
  for(const line of lines){
   ctx.beginPath();let previous;
   for(const p of line){const x=p[0]*scale,y=size-p[1]*scale;
    if(previous&&Math.abs(p[0]-previous[0])<n/2&&Math.abs(p[1]-previous[1])<n/2)ctx.lineTo(x,y);else ctx.moveTo(x,y);previous=p;}
   ctx.stroke();
   const spacing=Math.max(12,Math.round(65/(.65*scale)));
   for(let i=Math.floor(spacing/2);i<line.length-1;i+=spacing){
    const p=line[i],[u,v]=velocity(frame,...p),speed=Math.hypot(u,v);if(!speed)continue;
    const x=p[0]*scale,y=size-p[1]*scale,dx=u/speed,dy=-v/speed;
    ctx.beginPath();ctx.moveTo(x+3.5*dx,y+3.5*dy);ctx.lineTo(x-2.5*dx-2*dy,y-2.5*dy+2*dx);ctx.lineTo(x-2.5*dx+2*dy,y-2.5*dy-2*dx);ctx.closePath();ctx.fill();
   }
  }
 }
 return {velocity,paths,draw};
})();
if(typeof module!=='undefined')module.exports=Streamlines;
