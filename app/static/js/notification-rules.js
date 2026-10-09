/* Pure rules for foreground sound; push scheduling remains server-side. */
((root)=>{
  const quiet=(clock,start,end)=>start===end?false:start<end?clock>=start&&clock<end:clock>=start||clock<end;
  function due(entries,day,clock,timestamp,prefs,played){
    if(!prefs.medication||quiet(clock,prefs.quiet_start,prefs.quiet_end))return [];
    const minute=Number(clock.slice(0,2))*60+Number(clock.slice(3));
    return entries.filter(e=>e.status==='unmarked'&&prefs.person_ids.includes(e.user_id)).flatMap(e=>{
      const age=minute-(Number(e.time.slice(0,2))*60+Number(e.time.slice(3)));
      if(age<0||age>120)return [];
      const key=`${day}:${e.id}`,first=played[key+':0'];
      if(first===undefined)return [{key:key+':0'}];
      if(prefs.repeat_minutes&&timestamp-first>=prefs.repeat_minutes*60000&&played[key+':1']===undefined)return [{key:key+':1'}];
      return [];
    });
  }
  const rules={quiet,due};root.JarvisNotificationRules=rules;
  if(typeof module!=='undefined')module.exports=rules;
})(typeof window!=='undefined'?window:globalThis);
