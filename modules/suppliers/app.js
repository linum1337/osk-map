'use strict';
const plural=(n,a)=>a[(n%100>10&&n%100<20)?2:n%10===1?0:n%10>=2&&n%10<=4?1:2];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const CENTER=[55.7558,37.6173],ALL_NETWORKS=Object.values(NETWORKS).filter(n=>n.is_network).sort((a,b)=>a.name.localeCompare(b.name,'ru'));
const STORAGE='telecom-network-visibility-v1';
let stored={};try{stored=JSON.parse(localStorage.getItem(STORAGE)||'{}')}catch{}
// New networks remain visible. Only explicit hidden choices are persisted.
const hiddenNetworks=new Set((stored.hidden||[]).filter(k=>NETWORKS[k]?.is_network));
let showIndependent=stored.independent!==false;
const manufacturerKeys=new Set(SUPPLIERS.filter(d=>d.kind==='Производитель').map(d=>d.company_key).filter(Boolean));
const manufacturerOnly=document.getElementById('manufacturers-only');manufacturerOnly.checked=stored.manufacturers!==false;
const networkOf=d=>NETWORKS[d.company_key];
const locationOf=d=>[d.lat,d.lon<0?d.lon+360:d.lon];
const colorOf=d=>networkOf(d)?.is_network?networkOf(d).color:d.kind==='Производитель'?'#8052a0':/склад/i.test(d.kind)?'#087f73':'#2168a4';
function textColor(color){const c=color.replace('#','');const a=[0,2,4].map(i=>parseInt(c.slice(i,i+2),16)/255);return .2126*a[0]+.7152*a[1]+.0722*a[2]>.55?'#102f3e':'#ffffff'}
function pointType(d){return d.kind==='Производитель'?{cls:'factory',mark:'П'}:/склад/i.test(d.kind)?{cls:'warehouse',mark:d.kind==='Офис и склад'?'ОС':'С'}:d.kind==='Юридический адрес'?{cls:'legal',mark:'Ю'}:{cls:'office',mark:'О'}}
function clusterIcon(group){
 const children=group.getAllChildMarkers(),counts=new Map();
 for(const m of children){const k=m.options.networkKey||'independent';counts.set(k,(counts.get(k)||0)+1)}
 const ranked=[...counts].sort((a,b)=>b[1]-a[1]);
 let start=0;const segments=ranked.map(([k,n])=>{const end=start+n/children.length*100,c=k==='independent'?'#69828c':NETWORKS[k].color;const v=`${c} ${start}% ${end}%`;start=end;return v});
 const single=ranked.length===1,dominant=ranked[0][0],color=dominant==='independent'?'#69828c':NETWORKS[dominant].color;
 const label=single&&dominant!=='independent'?NETWORKS[dominant].name:'Несколько поставщиков';
 return L.divIcon({className:'network-cluster',iconSize:[44,44],html:`<div class="cluster-ring" style="background:${single?color:'conic-gradient('+segments.join(',')+')'}" title="${esc(label)} · ${children.length} точек"><span style="${single?'background:'+color+';color:'+textColor(color):''}">${children.length}</span></div>`});
}
const map=typeof L!=='undefined'?L.map('map',{scrollWheelZoom:true,zoomSnap:.25}).setView(CENTER,6):null;
let tilesLoaded=0,tileErrors=0,boundaryCircle=null;
if(map){
 const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>'}).addTo(map);
 tiles.on('tileload',()=>{tilesLoaded++;document.getElementById('maperror').style.display='none'});
 tiles.on('tileerror',()=>{tileErrors++;if(!tilesLoaded&&tileErrors>3)document.getElementById('maperror').style.display='block'});
 L.control.scale({imperial:false}).addTo(map);
 L.circleMarker(CENTER,{radius:4,color:'#173b48',weight:2,fillOpacity:1}).addTo(map).bindTooltip('Центр Москвы — начало отсчёта');
}else document.getElementById('maperror').style.display='block';
const cluster=map?(L.markerClusterGroup?L.markerClusterGroup({maxClusterRadius:38,spiderfyOnMaxZoom:true,animate:false,iconCreateFunction:clusterIcon}):L.layerGroup()).addTo(map):null;
const search=document.getElementById('search'),cat=document.getElementById('category'),kind=document.getElementById('kind'),region=document.getElementById('region'),radius=document.getElementById('radius'),district=document.getElementById('district'),profile=document.getElementById('profile');
let filtered=[],selected=null;const markers=new Map();
[...new Set(SUPPLIERS.map(d=>d.district))].sort().forEach(t=>district.add(new Option(t,t)));
[...new Set(SUPPLIERS.flatMap(d=>d.tags))].sort().forEach(t=>cat.add(new Option(t,t)));
function populateRegions(){const keep=region.value;region.innerHTML='<option value="">Все регионы</option>';[...new Set(SUPPLIERS.filter(d=>!district.value||d.district===district.value).map(d=>d.region))].sort((a,b)=>a.localeCompare(b,'ru')).forEach(t=>region.add(new Option(t,t)));if([...region.options].some(o=>o.value===keep))region.value=keep}
populateRegions();
function distance(d){return d.distance_km!=null?`≈ ${Math.round(d.distance_km)} км от Москвы`:''}
function persist(){try{localStorage.setItem(STORAGE,JSON.stringify({hidden:[...hiddenNetworks],independent:showIndependent,manufacturers:manufacturerOnly.checked}))}catch{}}
function networkVisible(d){return networkOf(d)?.is_network?!hiddenNetworks.has(d.company_key):showIndependent}
function matchesFilters(d){const q=search.value.trim().toLocaleLowerCase('ru');return(!manufacturerOnly.checked||manufacturerKeys.has(d.company_key))&&(!q||[d.name,networkOf(d)?.name,d.address,d.region,d.tags.join(' '),d.note].join(' ').toLocaleLowerCase('ru').includes(q))&&(!cat.value||d.tags.includes(cat.value))&&(!kind.value||d.kind===kind.value)&&(!region.value||d.region===region.value)&&(!district.value||d.district===district.value)&&(!profile.value||d.profile===profile.value)&&(radius.value==='all'||d.distance_km<=Number(radius.value))}
function oneNetwork(key){if(!NETWORKS[key]?.is_network)return;ALL_NETWORKS.forEach(n=>hiddenNetworks.add(n.id));hiddenNetworks.delete(key);showIndependent=false;search.value='';cat.value='';kind.value='';profile.value='';district.value='';region.value='';radius.value='all';populateRegions();persist();render(true)}
function popup(d){const n=networkOf(d),c=colorOf(d);return `<h2>${esc(d.name)}</h2>${n?.is_network?`<div class="popup-network"><span class="swatch" style="background:${c}"></span>${esc(n.name)} · ${n.point_count} адресов${n.corporate_color?'':' · условный цвет'}</div>`:''}<span class="tag">${esc(d.kind)}</span><p>${esc(d.address)}</p><p><strong>${distance(d)}</strong> · по прямой</p><p>${d.tags.map(esc).join(' · ')}</p>${d.note?`<p class="note">${esc(d.note)}</p>`:''}<p class="precision">${esc(d.precision)}</p><p class="note">${esc(d.source_type)} · проверено ${esc(d.checked)}<br>${esc(d.address_status)}</p><p>${d.phone?`<a href="tel:${d.phone.split(/;|доб\.|добавочный/)[0].replace(/[^+0-9]/g,'')}">${esc(d.phone)}</a>`:'Телефон не опубликован — см. источник'}</p><div class="links">${d.website?`<a href="${esc(d.website)}" target="_blank" rel="noopener">Сайт компании ↗</a>`:'<span class="note">Собственный сайт не подтверждён</span>'}<a href="${esc(d.source)}" target="_blank" rel="noopener">Источник / контакты ↗</a><a href="https://yandex.ru/maps/?text=${encodeURIComponent(d.address)}" target="_blank" rel="noopener">Адрес / маршрут ↗</a>${n?.is_network?`<button class="network-focus" data-network="${esc(n.id)}">Показать все адреса этой сети</button>`:''}</div>`}
function select(d){selected=d.id;document.querySelectorAll('.row').forEach(e=>e.classList.toggle('selected',Number(e.dataset.id)===selected));const m=markers.get(d.id);if(m&&map){if(cluster.zoomToShowLayer)cluster.zoomToShowLayer(m,()=>{map.setView(m.getLatLng(),Math.max(map.getZoom(),12));m.openPopup()});else{map.setView(m.getLatLng(),13);m.openPopup()}}}
function fit(){if(map){const points=filtered.filter(d=>d.lat!=null).map(locationOf);if(points.length)map.fitBounds(points,{padding:[35,35],maxZoom:13,animate:false})}}
function updateNetworkPanel(){
 const visible=ALL_NETWORKS.filter(n=>!hiddenNetworks.has(n.id)).length,master=document.getElementById('all-networks');master.checked=visible===ALL_NETWORKS.length;master.indeterminate=visible>0&&visible<ALL_NETWORKS.length;
 document.getElementById('independent').checked=showIndependent;
 document.getElementById('network-summary').textContent=`Филиальные сети · ${visible} из ${ALL_NETWORKS.length}`;
 const q=document.getElementById('network-search').value.trim().toLocaleLowerCase('ru'),list=document.getElementById('network-list');list.replaceChildren();
 const eligible=SUPPLIERS.filter(matchesFilters),counts=new Map();for(const d of eligible)counts.set(d.company_key,(counts.get(d.company_key)||0)+1);
 ALL_NETWORKS.filter(n=>!q||n.name.toLocaleLowerCase('ru').includes(q)).forEach(n=>{
  const line=document.createElement('div');line.className='network-row';const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!hiddenNetworks.has(n.id);check.setAttribute('aria-label',`Сеть ${n.name}`);check.onchange=()=>{if(check.checked)hiddenNetworks.delete(n.id);else hiddenNetworks.add(n.id);persist();render()};
  const sw=document.createElement('span');sw.className='swatch';sw.style.background=n.color;sw.title=n.corporate_color?'Цвет оформления официального сайта':'Условный цвет: фирменный не подтверждён';
  const text=document.createElement('span');text.className='network-name';text.textContent=n.name;const count=document.createElement('small');count.textContent=`${counts.get(n.id)||0} / ${n.point_count}`;count.title='Адресов по текущим фильтрам / всего в сети';
  label.append(check,sw,text,count);const only=document.createElement('button');only.textContent='Только';only.title=`Показать только сеть ${n.name}`;only.onclick=()=>oneNetwork(n.id);line.append(label,only);list.append(line)
 });
 if(!list.children.length)list.textContent='Сеть с таким названием не найдена.';
}
function render(autoFit=false){
 if(map){if(boundaryCircle)map.removeLayer(boundaryCircle);boundaryCircle=radius.value==='all'?null:L.circle(CENTER,{radius:Number(radius.value)*1000,color:'#367b86',weight:1.5,dashArray:'7 6',fillOpacity:.025,interactive:false}).addTo(map)}
 filtered=SUPPLIERS.filter(d=>matchesFilters(d)&&networkVisible(d));cluster?.clearLayers();markers.clear();const list=document.getElementById('list');list.replaceChildren();
 const count=filtered.length,companies=new Set(filtered.map(d=>d.company_key)).size,hidden=SUPPLIERS.filter(d=>matchesFilters(d)&&!networkVisible(d)).length;
 document.getElementById('count').textContent=`${companies} ${plural(companies,['компания','компании','компаний'])} · ${count} ${plural(count,['точка','точки','точек'])}${hidden?' · скрыто '+hidden:''}`;
 filtered.forEach(d=>{
  const row=document.createElement('button');row.className='row';row.dataset.id=d.id;const n=networkOf(d),color=colorOf(d);row.style.setProperty('--company-color',color);
  row.innerHTML=`<strong>${n?.is_network?`<span class="swatch" style="background:${color}"></span>`:''}${esc(d.name)}</strong><small>${esc(d.address)}</small><span class="tag">${esc(d.kind)}</span> <span class="tag">${distance(d)}</span><small>${d.tags.map(esc).join(' · ')}</small>`;
  row.onclick=()=>select(d);list.append(row);
  if(map&&d.lat!=null){const type=pointType(d),approx=!['Геокодирование адреса','Координаты компании'].includes(d.precision);
   const m=L.marker(locationOf(d),{title:`${n?.name||d.name} · ${d.kind} · ${d.address}`,networkKey:n?.is_network?n.id:null,icon:L.divIcon({className:'point-marker',html:`<span class="pin-shape ${type.cls}${approx?' approx':''}" style="--pin-color:${color};--pin-text:${textColor(color)}"><b>${type.mark}</b></span>`,iconSize:[32,32],iconAnchor:[16,16]})}).bindPopup(popup(d));
   m.on('popupopen',()=>{const btn=m.getPopup().getElement().querySelector('.network-focus');if(btn)btn.onclick=()=>oneNetwork(btn.dataset.network)});
   m.on('click',()=>{selected=d.id;document.querySelectorAll('.row').forEach(e=>e.classList.toggle('selected',Number(e.dataset.id)===selected))});markers.set(d.id,m);cluster.addLayer(m)
  }
 });
 if(!count)list.innerHTML='<p class="empty">Нет видимых точек по выбранным условиям. Проверьте фильтры и включённые сети.</p>';
 updateNetworkPanel();if(autoFit)fit();
}
manufacturerOnly.onchange=()=>{persist();render(true)};
search.addEventListener('input',()=>render());[cat,kind,region,radius,profile].forEach(e=>e.onchange=()=>render(true));district.onchange=()=>{region.value='';populateRegions();render(true)};
document.getElementById('network-search').oninput=updateNetworkPanel;
document.getElementById('all-networks').onchange=e=>{ALL_NETWORKS.forEach(n=>e.target.checked?hiddenNetworks.delete(n.id):hiddenNetworks.add(n.id));persist();render()};
document.getElementById('independent').onchange=e=>{showIndependent=e.target.checked;persist();render()};
document.getElementById('enable-networks').onclick=()=>{hiddenNetworks.clear();persist();render()};
document.getElementById('disable-networks').onclick=()=>{ALL_NETWORKS.forEach(n=>hiddenNetworks.add(n.id));persist();render()};
document.getElementById('fit').onclick=fit;
document.getElementById('boundary').onclick=()=>{search.value='';cat.value='';kind.value='';region.value='';district.value='';profile.value='';radius.value='all';hiddenNetworks.clear();showIndependent=true;populateRegions();persist();render(true)};
document.getElementById('headline').textContent=`${Object.keys(NETWORKS).length} ${plural(Object.keys(NETWORKS).length,['компания','компании','компаний'])} · ${SUPPLIERS.length} ${plural(SUPPLIERS.length,['адрес','адреса','адресов'])} · ${ALL_NETWORKS.length} ${plural(ALL_NETWORKS.length,['филиальная сеть','филиальные сети','филиальных сетей'])}`;
render();fit();

document.getElementById('legend-networks').onclick=e=>{e.preventDefault();document.getElementById('net-panel').open=true;document.getElementById('net-panel').scrollIntoView({block:'nearest',behavior:'smooth'})};
