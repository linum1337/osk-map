(()=>{
const colors={'Логинов Андрей':'#042e65','Скрынник Анна':'#d62828','Квашина Светлана':'#00a0dd','Коровина Любовь':'#ef6c00'};
window.managerColors=colors;window.activeManagers=new Set(Object.keys(colors));
const link=document.createElement('link');link.rel='stylesheet';link.href='transport-theme.css';document.head.append(link);
const header=document.querySelector('header'),top=document.createElement('div');top.className='header-top';while(header.firstChild)top.append(header.firstChild);header.append(top);
const chips=document.createElement('fieldset');chips.id='manager-chips';chips.innerHTML='<legend>Менеджеры на карте и в таблице</legend>'+Object.entries(colors).map(([m,c])=>`<label class="manager-choice"><input type="checkbox" value="${esc(m)}" checked><b class="manager-swatch" style="background:${c}">${m.split(' ').map(s=>s[0]).join('')}</b><span>${esc(m)}</span><small data-owner-count="${esc(m)}">40</small></label>`).join('')+'<div class="manager-actions"><button type="button" id="managers-all">Все</button><button type="button" id="managers-none">Скрыть все</button></div>';header.append(chips);
const previous=update;update=function(...args){previous(...args);matches=matches.filter(x=>window.activeManagers.has(x.manager));drawMarkers();syncViewport()};
function refresh(){window.activeManagers=new Set([...chips.querySelectorAll('input:checked')].map(x=>x.value));update();document.dispatchEvent(new Event('manager-visibility-change'))}
chips.querySelectorAll('input').forEach(x=>x.onchange=refresh);$('managers-all').onclick=()=>{chips.querySelectorAll('input').forEach(x=>x.checked=true);refresh()};$('managers-none').onclick=()=>{chips.querySelectorAll('input').forEach(x=>x.checked=false);refresh()};
const oldList=list;list=function(){oldList();$('list').querySelectorAll('.card').forEach((card,i)=>{const x=filtered[i];if(!x?.manager)return;const tag=document.createElement('div');tag.className='manager-tag';tag.innerHTML=`<i class="manager-dot" style="background:${colors[x.manager]||'#64748b'}"></i>${esc(x.manager)}`;card.append(tag)});chips.querySelectorAll('[data-owner-count]').forEach(e=>e.textContent=D.filter(x=>x.manager===e.dataset.ownerCount).length)};
$('reset').addEventListener('click',()=>{chips.querySelectorAll('input').forEach(x=>x.checked=true);$('crm-manager').value='';refresh()});
update();map.invalidateSize();
})();
