const assert=require('node:assert/strict');
const S=require('../web/streamlines.js');
const n=64;
const uniform={n,u:new Float32Array(n*n).fill(1),v:new Float32Array(n*n),speed_max:1};
assert.deepEqual(S.velocity(uniform,-.2,64.8),[1,0]);
const lines=S.paths(uniform);
assert(lines.length>0);
for(const line of lines){
 const y=line[0][1];
 for(const p of line)assert(Math.abs(p[1]-y)<1e-10);
 for(let i=1;i<line.length;i++)assert(Math.abs(((line[i][0]-line[i-1][0]+n)%n)-.65)<1e-9);
}
assert.deepEqual(S.paths({...uniform,speed_max:0}),[]);
// A periodic Taylor–Green vortex: arrows must be tangent to streamfunction contours.
const u=new Float32Array(n*n),v=new Float32Array(n*n);
for(let j=0;j<n;j++)for(let i=0;i<n;i++){const x=i*2*Math.PI/n,y=j*2*Math.PI/n;u[j*n+i]=Math.sin(x)*Math.cos(y);v[j*n+i]=-Math.cos(x)*Math.sin(y);}
const vortex={n,u,v,speed_max:1};
let maximumDrift=0;
for(const line of S.paths(vortex)){
 const psi=([x,y])=>Math.sin(x*2*Math.PI/n)*Math.sin(y*2*Math.PI/n);
 const initial=psi(line[0]);
 for(const p of line)maximumDrift=Math.max(maximumDrift,Math.abs(psi(p)-initial));
}
assert(maximumDrift<.015,`Streamline crosses contours: ${maximumDrift}`);
console.log(`Streamline checks passed: periodicity, direction, zero field, contour drift=${maximumDrift.toFixed(5)}`);
