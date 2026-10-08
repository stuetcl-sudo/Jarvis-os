/* Appearance persistence must be robust without storage and follow OS only in system mode. */
const test=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');
const source=fs.readFileSync('app/static/js/theme.js','utf8');
function start(saved,{dark=false,blocked=false}={}){
 const listeners={},system={matches:dark,addEventListener:(_,fn)=>listeners.system=fn};const root={dataset:{}};const selects=[],metas=[{content:'',removeAttribute(){}}];
 const document={documentElement:root,querySelectorAll:s=>s==='[data-theme-select]'?selects:s.startsWith('meta')?metas:[],addEventListener:(_,fn)=>listeners.ready=fn};
 const writes=[];const storage={getItem(){if(blocked)throw Error('blocked');return saved;},setItem(k,v){if(blocked)throw Error('blocked');writes.push([k,v]);}};
 const window={matchMedia:()=>system,addEventListener:(name,fn)=>listeners[name]=fn};
 vm.runInNewContext(source,{document,window,localStorage:storage});return {root,listeners,system,selects,writes};
}
test('explicit light survives dark OS and OS changes',()=>{const s=start('light',{dark:true});assert.equal(s.root.dataset.jarvisTheme,'light');s.system.matches=false;s.listeners.system();s.system.matches=true;s.listeners.system();assert.equal(s.root.dataset.jarvisTheme,'light');assert.deepEqual(s.writes,[]);});
test('system follows changing OS without persisting an override',()=>{const s=start('system');assert.equal(s.root.dataset.jarvisTheme,'light');s.system.matches=true;s.listeners.system();assert.equal(s.root.dataset.jarvisTheme,'dark');assert.deepEqual(s.writes,[]);});
test('invalid preference and blocked storage use system safely',()=>{for(const opt of [{},{blocked:true}]){const s=start('invalid',{...opt,dark:true});assert.equal(s.root.dataset.jarvisAppearance,'system');assert.equal(s.root.dataset.jarvisTheme,'dark');}});
test('another tab updates selects; clearing preference restores system',()=>{const s=start('light');const select={value:'light'};s.selects.push(select);s.listeners.storage({key:'unrelated',newValue:'dark'});assert.equal(s.root.dataset.jarvisTheme,'light');s.listeners.storage({key:'jarvis.appearance',newValue:'dark'});assert.equal(select.value,'dark');assert.equal(s.root.dataset.jarvisTheme,'dark');s.listeners.storage({key:null,newValue:null});assert.equal(select.value,'system');assert.equal(s.root.dataset.jarvisTheme,'light');});
