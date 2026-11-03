const D=window.PROVIDERS.filter(window.inWorkArea),$=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safe=u=>/^https?:\/\//i.test(u)?u:'';const map=L.map('map',{minZoom:2,maxZoom:19}).setView([55,44],4);
map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
const tileUrl=location.protocol==='file:'?'https://tile.openstreetmap.org/{z}/{x}/{y}.png':'/tiles/{z}/{x}/{y}.png';
const tile=L.tileLayer(tileUrl,{attribution:'© OpenStreetMap contributors · HOT',maxZoom:19}).addTo(map);
tile.on('tileerror',()=>{$('tileError').hidden=false});tile.on('tileload',()=>{$('tileError').hidden=true});
const layer=L.layerGroup().addTo(map);
function mapPosition(x){if(Number.isFinite(x.lat)&&Number.isFinite(x.lon))return {lat:x.lat,lon:x.lon,approximate:false};const p=(window.CITY_CENTRES||{})[x.officeId];return p?{lat:p.lat,lon:p.lon,approximate:true}:null}

const uniq=a=>[...new Set(a)].sort((a,b)=>a.localeCompare(b,'ru'));
function fill(id,values){const s=$(id),old=s.value;s.innerHTML='<option value="">'+({district:'Все округа',region:'Все регионы',service:'Все виды услуг'}[id])+'</option>'+values.map(v=>`<option>${esc(v)}</option>`).join('');if(values.includes(old))s.value=old}
fill('district',uniq(D.map(x=>x.district)));fill('region',uniq(D.map(x=>x.region)));fill('service',uniq(D.flatMap(x=>x.services)));
let filtered=[],matches=[],shown=160;const local=x=>x.group.startsWith('Местные');
function popup(x){const approx=mapPosition(x)?.approximate;return `${approx?'<p class="approx-warning">≈ Около центра города. Адрес офиса и координаты не подтверждены.</p>':''}<h3>${esc(x.name)}</h3><div>${esc(x.city)} · ${esc(x.region)}</div><p><b>${esc(x.address||'Офисный адрес не подтверждён')}</b><br>${esc(x.officeType||'')}<br>${esc(x.phone||'')}</p><div class="muted">${esc(x.group)}</div><div class="tags">${x.services.map(s=>`<span class="tag">${esc(s)}</span>`).join('')}</div><p class="muted">${esc(x.precision)} · сбор ${esc(x.checked)}<br>${esc(x.addressStatus||'Не проверен')}<br><b>${esc(x.visitNote||'Приём посетителей уточняйте перед визитом.')}</b><br>Услуги оператора указаны по каталогу и карточкам организаций. Возможности конкретного офиса уточняйте перед визитом.</p>${safe(x.website)?`<a class="popup-link" target="_blank" rel="noopener" href="${esc(safe(x.website))}">Сайт оператора ↗</a>`:'<span class="website-missing">Сайт пока не указан</span>'}<a class="popup-link" target="_blank" rel="noopener" href="${esc(safe(x.source))}">${x.office?'Источник адреса':'Источник каталога'} ↗</a>`}
const basePopup=popup;popup=function(x){return basePopup(x)+(x.yandexSource?`<a class="popup-link" target="_blank" rel="noopener" href="${esc(safe(x.yandexSource))}">Яндекс Карты ↗</a>`:'')+(x.officialSource?`<a class="popup-link" target="_blank" rel="noopener" href="${esc(safe(x.officialSource))}">Сайт: адрес офиса ↗</a>`:'');};
function focus(x){const p=mapPosition(x);if(p){map.setView([p.lat,p.lon],p.approximate?12:17);L.popup().setLatLng([p.lat,p.lon]).setContent(popup(x)).openOn(map)}else{const d=document.createElement('dialog');d.innerHTML=popup(x)+'<p>Город или координаты пока не определены.</p><button>Закрыть</button>';document.body.append(d);d.querySelector('button').onclick=()=>{d.close();d.remove()};d.showModal()}}
function websiteLink(x){const u=safe(x.website);if(!u)return '<div class="website-missing">Сайт пока не указан</div>';let label;try{label=new URL(u).hostname.replace(/^www[.]/,'')}catch{return '<div class="website-missing">Сайт пока не указан</div>'}return `<a class="website-link" href="${esc(u)}" target="_blank" rel="noopener noreferrer" aria-label="Сайт ${esc(x.name)}: ${esc(label)}">${esc(label)} ↗</a>`}
function list(){const div=$('list');div.innerHTML='';if(!filtered.length){div.innerHTML='<div class="empty">В этой области нет компаний по выбранным фильтрам. Отдалите или переместите карту либо отключите фильтр «В видимой области карты».</div>';return}filtered.slice(0,shown).forEach(x=>{const a=document.createElement('article');a.className='card';a.tabIndex=0;a.innerHTML=`<h3>${esc(x.name)}</h3><div class="muted">${esc(x.city)} · ${esc(x.region)}</div><div class="muted">${esc(x.address||'Офисный адрес не подтверждён')}</div>${websiteLink(x)}${mapPosition(x)?.approximate?'<div class="approx-note">≈ У центра города · адрес не подтверждён</div>':''}<div class="tags"><span class="tag ${local(x)?'local':'federal'}">${x.fromBitrix?'Компания из Битрикс24':local(x)?'Местный / региональный':'Федеральная сеть'}</span>${x.services.map(s=>`<span class="tag">${esc(s)}</span>`).join('')}</div>`;a.onclick=e=>{if(!e.target.closest('a'))focus(x)};a.onkeydown=e=>{if(e.target===a&&e.key==='Enter')focus(x)};div.append(a)});if(filtered.length>shown){const b=document.createElement('button');b.textContent=`Показать ещё (${filtered.length-shown})`;b.style.margin='15px';b.onclick=()=>{shown+=160;list()};div.append(b)}}
function syncViewport(){
 const bounds=map.getBounds();
 filtered=$('inview').checked?matches.filter(x=>{const p=mapPosition(x);return p&&bounds.contains([p.lat,p.lon])}):matches;
 shown=160;
 $('count').textContent=`Адресов ${$('inview').checked?'в видимой области':'по выбранным фильтрам'}: ${filtered.length.toLocaleString('ru')} · компаний: ${new Set(filtered.map(x=>x.id)).size}`;
 $('brands').textContent=new Set(filtered.map(x=>x.id)).size;
 $('places').textContent=new Set(filtered.map(x=>x.city)).size;
 $('localcount').textContent=new Set(filtered.filter(local).map(x=>x.id)).size;
 list();
}
function drawMarkers(){
 layer.clearLayers();
 // Merge nearby screen positions until the resulting symbols do not overlap.
 let groups=matches.map(x=>{const p=mapPosition(x);if(!p)return null;const at=map.latLngToLayerPoint([p.lat,p.lon]);return {xs:[x],px:at.x+(p.approximate?28:0),py:at.y-(p.approximate?28:0)}}).filter(Boolean);
 let again=true;
 while(again){again=false;const merged=[];
  for(const g of groups){const near=merged.find(h=>(h.px-g.px)**2+(h.py-g.py)**2<48**2);if(near){const n=near.xs.length,m=g.xs.length;near.px=(near.px*n+g.px*m)/(n+m);near.py=(near.py*n+g.py*m)/(n+m);near.xs.push(...g.xs);again=true}else merged.push(g)}groups=merged;
 }
 groups.forEach(g=>{
  const xs=g.xs,x=xs[0],size=36,approx=xs.every(p=>mapPosition(p)?.approximate),partApprox=xs.some(p=>mapPosition(p)?.approximate),at=map.layerPointToLatLng([g.px,g.py]);
  const names=uniq(xs.map(p=>p.name)),owners=uniq(xs.map(p=>p.manager).filter(Boolean)),color=owners.length===1?(window.managerColors||{})[owners[0]]||'#1959a6':'#52667e';
  const marker=L.marker(at,{icon:L.divIcon({className:'',html:`<div class="cluster ${approx?'approximate':''}" style="width:${size}px;height:${size}px;background:${color}">${xs.length===1&&approx?'≈':xs.length}</div>`,iconSize:[size,size],iconAnchor:[size/2,size/2]})}).addTo(layer);
  if(xs.length===1)marker.bindPopup(popup(x),{maxWidth:380});
  else{
   marker.bindPopup(`<h3>Компаний рядом: ${xs.length}</h3>${partApprox?'<div class="approx-warning">Есть условные отметки около центра города. Они не обозначают адрес офиса.</div>':''}<div class="provider-choices">`+xs.map((p,i)=>`<button class="provider-choice" data-p="${i}"><strong>${esc(p.name)}</strong><span>${esc(p.city)} · ${mapPosition(p)?.approximate?'≈ Центр города · адрес не подтверждён':esc(p.address||'Адресная точка')}</span></button>`).join('')+'</div>',{maxWidth:380});
   marker.on('popupopen',e=>e.popup.getElement().querySelectorAll('[data-p]').forEach(a=>a.onclick=ev=>{ev.preventDefault();focus(xs[Number(a.dataset.p)])}));
  }
  marker.bindTooltip((xs.length>6?`Компаний: ${xs.length}<br>`+names.slice(0,6).map(esc).join('<br>')+'<br>…':names.map(esc).join('<br>'))+(partApprox?'<br>≈ Есть условные отметки по городу':''),{direction:'top',offset:[0,-16]});
 });
}
function update(fitIfOutside=false){
 const q=$('q').value.toLowerCase().replace(/ё/g,'е');
 matches=D.filter(x=>(!$('offices').checked||(x.lat!=null&&x.lon!=null))&&(!$('local').checked||local(x)||x.fromBitrix)&&(!$('district').value||x.district===$('district').value)&&(!$('region').value||x.region===$('region').value)&&(!$('service').value||x.services.includes($('service').value))&&(!q||[x.name,x.city,x.region,x.address].join(' ').toLowerCase().replace(/ё/g,'е').includes(q))).sort((a,b)=>Number(local(b))-Number(local(a))||a.name.localeCompare(b.name,'ru'));
 drawMarkers();
 const points=matches.map(mapPosition).filter(Boolean).map(p=>[p.lat,p.lon]);
 if(fitIfOutside&&points.length&&!points.some(p=>map.getBounds().contains(p))){map.fitBounds(points,{padding:[60,60],maxZoom:16});}
 syncViewport();
}
map.on('moveend',syncViewport);map.on('zoomend',drawMarkers);
['service','local','offices'].forEach(id=>$(id).addEventListener('change',()=>update()));
$('q').addEventListener('input',()=>update(true));
$('region').addEventListener('change',()=>update(true));
$('inview').addEventListener('change',syncViewport);
$('district').onchange=()=>{fill('region',uniq(D.filter(x=>!$('district').value||x.district===$('district').value).map(x=>x.region)));update(true)};
$('reset').onclick=()=>{$('q').value='';$('district').value='';fill('region',uniq(D.map(x=>x.region)));$('region').value='';$('service').value='';$('local').checked=true;$('offices').checked=false;$('inview').checked=true;map.setView([55,44],4);update()};
$('about').onclick=$('method').onclick=e=>{e.preventDefault();$('info').showModal()};$('close').onclick=()=>$('info').close();update();
