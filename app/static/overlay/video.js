"use strict";
const cameraArea=new URLSearchParams(location.search).get("camera")==="corrected"?"board_corrected":"raw";
startBoardFeed(document.getElementById("webcam-video"), cameraArea);
