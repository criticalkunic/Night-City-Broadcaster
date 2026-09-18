"use strict";
// Render at OBS's 1080p viewport, then shrink the complete frame to its panel.
for (const frame of document.querySelectorAll('.preview iframe')) {
 const container=frame.parentElement;
 Object.assign(frame.style,{width:'1920px',height:'1080px',transformOrigin:'top left',position:'absolute',left:'0',top:'0',border:'0'});
 const resize=()=>{frame.style.transform=`scale(${container.clientWidth/1920})`;};
 new ResizeObserver(resize).observe(container);
 resize();
}
