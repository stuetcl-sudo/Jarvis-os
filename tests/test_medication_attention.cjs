const assert=require('node:assert/strict');const {evaluate}=require('../app/static/js/medication-attention.js');
const entries=[{id:'1',time:'07:00',status:'unmarked'},{id:'2',time:'07:30',status:'taken'},{id:'3',time:'07:40',status:'skipped'},{id:'4',time:'09:00',status:'unmarked'}];
assert.deepEqual(evaluate(entries,'2026-10-08',new Date('2026-10-08T05:52:00Z')).map(e=>[e.id,e.lateMinutes]),[['1',52]]);
assert.equal(evaluate(entries,'2026-10-07',new Date('2026-10-08T05:52:00Z')).length,0);
assert.equal(evaluate(entries,'2026-10-08',new Date('2026-10-08T04:00:00Z')).length,0);
assert.equal(evaluate(entries,'2026-10-08',new Date('2026-10-08T05:00:00Z'))[0].lateMinutes,0);
assert.equal(evaluate(entries,'2026-10-08',new Date('2026-10-08T23:00:00Z')).length,0);
console.log('Medication attention: household timezone, midnight, later slots, taken/skipped and exact time passed.');
