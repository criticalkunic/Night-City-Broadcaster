const net=require('node:net');
function reserve(port){return new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(port,'127.0.0.1',()=>{const selected=server.address().port;server.close(error=>error?reject(error):resolve(selected));});});}
async function choosePort(preferred=8766){try{return await reserve(preferred);}catch(error){if(error.code!=='EADDRINUSE')throw error;return reserve(0);}}
module.exports={choosePort};
