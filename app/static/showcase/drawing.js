'use strict';
window.renderShowcaseDrawings=function(svg,strokes){
 svg.replaceChildren();
 for(const stroke of strokes||[]){const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',stroke.points.map(([x,y])=>`${x*1600},${y*900}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke',stroke.color);line.setAttribute('stroke-width',String(stroke.thickness||5));line.setAttribute('stroke-linecap','round');line.setAttribute('stroke-linejoin','round');svg.append(line);}
};

// The image uses object-fit:contain; compute additional scaling to fill its frame.
window.showcaseBoardTransform=function(display,corrected,sourceWidth,sourceHeight,frameWidth,frameHeight){
 if(!corrected)return 'none';
 const x=(display.corrected_width||100)/100,y=(display.corrected_height||100)/100;
 let fill=1;
 if(display.corrected_fit!=='contain'&&sourceWidth>0&&sourceHeight>0&&frameWidth>0&&frameHeight>0){
  const fit=Math.min(frameWidth/sourceWidth,frameHeight/sourceHeight);
  fill=Math.max(frameWidth/(sourceWidth*fit*x),frameHeight/(sourceHeight*fit*y));
 }
 const zoom=(display.corrected_zoom||100)/100;
 return `translate(${display.corrected_x||0}%,${display.corrected_y||0}%) scale(${x*fill*zoom},${y*fill*zoom})`;
};
window.applyShowcaseBoardTransform=function(image,svg,display,corrected){
 const transform=showcaseBoardTransform(display,corrected,image.naturalWidth,image.naturalHeight,image.clientWidth,image.clientHeight);
 image.style.transform=transform;svg.style.transform=transform;
};
