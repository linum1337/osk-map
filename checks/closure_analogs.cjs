const assert=require('node:assert/strict');const fs=require('node:fs'),path=require('node:path');const {ClosureAnalogues:A}=require('../app/references/closures/analogs.js');
const source={name:'Муфта оптическая тупиковая TEST',fields:{layout:'Тупиковая',capacity:'144',ports:'4',portSeal:'ТУТ',bodySeal:'Хомут',transit:'Да',ip:'IP68',temperature:'от минус 60 °C до 70 °C'}};
const req={kind:'dome',capacity:144,ports:4,portSeal:'heat',bodySeal:'mechanical',transit:true,ip:'IP68',temperatureLow:-60,temperatureHigh:70};
assert(A.matches(source,req));
for(const change of [{layout:'Проходная'},{capacity:'96'},{ports:'2'},{portSeal:'Механическая'},{bodySeal:'ТУТ'},{transit:'Нет'},{ip:'IP65'},{temperature:'от -40 до +65'}]){const e={...source,name:'TEST',fields:{...source.fields,...change}};assert(!A.matches(e,req),JSON.stringify(change))}
assert(!A.matches({...source,name:'Муфта-кросс',fields:{...source.fields}},req));
for(const key of ['capacity','ports','portSeal','bodySeal','transit','ip','temperature']){const fields={...source.fields};delete fields[key];assert(!A.matches({name:'TEST',fields},req),'unknown '+key)}
assert(!A.matches({...source,fields:{...source.fields,portSeal:'ТУТ, механическая герметизация'}},req));assert(A.matches({...source,fields:{...source.fields,portSeal:'ТУТ, механическая герметизация'}},{...req,portSeal:'mixed'}));assert(!A.matches({...source,fields:{...source.fields,cableDiameter:'круглые 4×Ø10...18 мм (механическая герметизация)'}},req));
assert(A.matches({...source,fields:{...source.fields,capacity:'216',ports:'6'}},req));
assert.equal(A.capacity('48/96 (два слоя)'),96);assert.equal(A.ports('4 (круглый), 1 (овальный)'),5);assert.equal(A.ports('4/2/1'),null);
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'../app/references/closures/closures.json')));const baseline=data.entries.find(e=>e.id==='42c2d2a4013dee84');const p=A.profile(baseline);assert.equal(p.kind,'dome');assert.equal(p.capacity,144);assert.equal(p.ports,5);const demands={kind:p.kind,capacity:p.capacity,portSeal:p.portSeals[0],transit:p.transit};const matches=data.entries.filter(e=>e.id!==baseline.id&&A.matches(e,demands));assert(matches.length>0);assert(matches.every(e=>A.profile(e).kind==='dome'&&A.profile(e).capacity>=144));console.log('PASS: closure candidates exclude different construction, lower capacity/input count, wrong seals, missing transit, weaker IP/climate and unknown required parameters; real model candidates remain');

const sourceData=JSON.parse(require('fs').readFileSync(require('path').join(__dirname,'../app/references/closures/closures.json'),'utf8'));
const enrichedFind=id=>sourceData.entries.find(e=>e.id===id);
require('assert').equal(A.capacity('до 54'),54);
require('assert').equal(A.profile(enrichedFind('dcafe05f1e6fa7d2')).capacity,48);
require('assert').equal(enrichedFind('4d29814103d4d9a6').fields.capacity,'144');
require('assert').equal(enrichedFind('2e2a004404e17e32').fields.capacity,'216');
const chosen=enrichedFind('4d29814103d4d9a6');
require('assert').equal(A.matches(chosen,{minimums:{cassettesMax:999}}),false);
require('assert').equal(A.matches(chosen,{supplier:'НАГ'}),false);
require('assert').equal(A.matches(chosen,{fields:{cassetteType:'NONEXISTENT'}}),false);
require('assert').equal(A.matches(chosen,{specifications:[{key:'Missing',value:'anything'}]}),false);
