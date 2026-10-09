const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function worker(){
 const handlers={}, shown=[], opened=[];let clients=[];
 const self={location:{origin:'https://jarvis.example'},addEventListener:(type,fn)=>handlers[type]=fn,registration:{showNotification:async(...args)=>shown.push(args)},clients:{matchAll:async()=>clients,openWindow:async url=>opened.push(url)}};
 vm.runInNewContext(fs.readFileSync('app/static/pwa/sw.js','utf8'),{self,URL,Response,fetch:async()=>{throw Error('offline');}});
 return {handlers,shown,opened,setClients:value=>clients=value};
}
function run(handler,event){let pending;handler({...event,waitUntil:p=>pending=p,respondWith:p=>pending=p});return pending;}
test('push limits text and refuses external destinations, including malformed payloads',async()=>{
 const w=worker();await run(w.handlers.push,{data:{json:()=>({title:'x'.repeat(200),body:'y'.repeat(600),url:'https://evil.example'})}});
 assert.equal(w.shown[0][0].length,100);assert.equal(w.shown[0][1].body.length,500);assert.equal(w.shown[0][1].data.url,'/#beskeder');
 await run(w.handlers.push,{data:{json:()=>{throw Error('invalid');}}});assert.equal(w.shown[1][0],'Jarvis');
});
test('click navigates an existing same-origin window or opens an allowed path',async()=>{
 const w=worker(),navigated=[];let focused=0,closed=0;
 w.setClients([{url:'https://other.example/'},{url:'https://jarvis.example/',navigate:async url=>navigated.push(url),focus:async()=>focused++}]);
 await run(w.handlers.notificationclick,{notification:{close:()=>closed++,data:{url:'/#medicin'}}});
 assert.deepEqual(navigated,['https://jarvis.example/#medicin']);assert.equal(focused,1);assert.equal(closed,1);
 w.setClients([]);await run(w.handlers.notificationclick,{notification:{close(){},data:{url:'//evil.example/'}}});assert.deepEqual(w.opened,['https://jarvis.example/#beskeder']);
});
test('offline navigation displays failure without cached household data; API calls bypass worker',async()=>{
 const w=worker();const response=await run(w.handlers.fetch,{request:{mode:'navigate'}});assert.equal(response.status,503);assert.match(await response.text(),/Ingen medicin eller afkrydsninger gemmes offline/);
 assert.equal(run(w.handlers.fetch,{request:{mode:'cors'}}),undefined);
});
