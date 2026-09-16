const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={window:{}};vm.runInNewContext(fs.readFileSync('app/static/setup/geometry.js','utf8'),context);
const size=(res,rect,points)=>Array.from(context.window.CameraSetupGeometry.correctedSize(res,rect,points));
const full={width:1,height:1},quad=[[0,0],[1,0],[1,1],[0,1]];
assert.deepEqual(size([1920,1080],full,quad),[800,450]);
assert.deepEqual(size([640,480],full,quad),[640,480]);
assert.deepEqual(size([1080,1920],full,quad),[450,800]);
assert.deepEqual(size([1920,1080],{width:.5,height:1},quad),[711,800]);
assert.deepEqual(size([1920,1080],full,[[.25,.25],[.75,.25],[.75,.75],[.25,.75]]),[800,450]);
// Exercise the actual drawing routine with a fake canvas: hidden future zones
// must not be painted; previous zones are dashed and have no handles.
const source=fs.readFileSync('app/static/setup/setup.js','utf8');
const drawn=[],handles=[];let color;
const ctx={set fillStyle(v){color=v;},fillText(){}};
const drawing={P1:'#cyan',P2:'#red',ACCENT:'#yellow',target:'p1_legend',guideTargets:['p1_card','p1_legend'],
 cal:{regions:{player1:{regions:{card_play_region:{id:'play'},legend_region:{id:'legend'},eddie_region:{id:'eddie'},gig_region:{id:'gig'},fixer_region:{id:'fixer'}}}}},
 syncCanvas:()=>[ctx,800,450],strokeRect:(ctx,rect,w,h,color,active)=>drawn.push([rect.id,active]),rectCorners:r=>r,drawHandles:(ctx,r)=>handles.push(r.id)};
vm.runInNewContext(source.slice(source.indexOf('const ROI_KEYS'),source.indexOf('/* ---------------- save / reload')),drawing);
vm.runInNewContext('drawRois(1)',drawing);
assert.deepEqual(drawn,[['play',false],['legend',true]]);assert.deepEqual(handles,['legend']);
console.log('Setup geometry: native proportions and progressive zone drawing passed.');
