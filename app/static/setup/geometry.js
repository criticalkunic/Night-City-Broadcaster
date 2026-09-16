'use strict';
window.CameraSetupGeometry = {
 correctedSize([width,height],rect,points){
  const w=width*rect.width,h=height*rect.height;
  const quad=(points||[[0,0],[1,0],[1,1],[0,1]]).map(([x,y])=>[x*w,y*h]);
  const edge=(a,b)=>Math.hypot(quad[a][0]-quad[b][0],quad[a][1]-quad[b][1]);
  const outW=Math.max(edge(0,1),edge(3,2),1),outH=Math.max(edge(0,3),edge(1,2),1);
  const scale=Math.min(1,800/Math.max(outW,outH));
  return [Math.max(64,Math.round(outW*scale)),Math.max(64,Math.round(outH*scale))];
 }
};
