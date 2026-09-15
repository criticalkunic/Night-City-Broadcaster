const assert=require('node:assert/strict'),net=require('node:net');
const {choosePort}=require('../desktop/port.cjs');
(async()=>{const busy=net.createServer();await new Promise(r=>busy.listen(0,'127.0.0.1',r));const port=busy.address().port;const alternative=await choosePort(port);assert.notEqual(alternative,port);assert(busy.listening);await new Promise(r=>busy.close(r));assert.equal(await choosePort(port),port);console.log('Port fallback passed; existing service remains untouched.');})().catch(e=>{console.error(e);process.exit(1);});
