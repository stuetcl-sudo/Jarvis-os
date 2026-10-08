/* Attention marks a missing registration, never a clinical severity or dose. */
((root)=>{
  function evaluate(entries,day,now=new Date(),zone='Europe/Copenhagen'){
    const parts=Object.fromEntries(new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
    const currentDay=`${parts.year}-${parts.month}-${parts.day}`;if(day!==currentDay)return[];
    const minutes=Number(parts.hour)*60+Number(parts.minute);
    return entries.filter(e=>e.status==='unmarked'&&/^([01]\d|2[0-3]):[0-5]\d$/.test(e.time)).map(e=>({...e,lateMinutes:minutes-(Number(e.time.slice(0,2))*60+Number(e.time.slice(3)))})).filter(e=>e.lateMinutes>=0).sort((a,b)=>b.lateMinutes-a.lateMinutes||a.id.localeCompare(b.id));
  }
  root.JarvisMedicationAttention={evaluate};if(typeof module!=='undefined')module.exports={evaluate};
})(globalThis);
