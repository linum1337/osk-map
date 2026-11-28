(()=>{'use strict';
const normalize=value=>String(value).toLocaleLowerCase('ru').replaceAll('ё','е').trim();
window.searchableSelect=select=>{
 const wrap=document.createElement('div');wrap.className='searchable-select';
 const input=document.createElement('input');input.type='text';input.id=select.id+'-search';input.autocomplete='off';input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');
 const list=document.createElement('div');list.id=select.id+'-suggestions';list.className='select-suggestions';list.setAttribute('role','listbox');list.hidden=true;input.setAttribute('aria-controls',list.id);
 const label=select.closest('label');if(label){const text=Array.from(label.childNodes).filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim();input.setAttribute('aria-label',text)}
 select.before(wrap);wrap.append(input,list,select);select.hidden=true;select.tabIndex=-1;
 let options=[],active=-1;
 function sync(){if(list.hidden)input.value=select.selectedOptions[0]?.textContent||''}
 function close(){list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');active=-1;sync()}
 function highlight(index){active=index;Array.from(list.children).forEach((node,i)=>node.setAttribute('aria-selected',String(i===index)));if(index>=0){input.setAttribute('aria-activedescendant',list.children[index].id);list.children[index].scrollIntoView({block:'nearest'})}else input.removeAttribute('aria-activedescendant')}
 function choose(option){select.value=option.value;close();select.dispatchEvent(new Event('change',{bubbles:true}))}
 function show(query=''){
  const term=normalize(query);options=Array.from(select.options).filter(o=>!o.disabled&&(!term||normalize(o.textContent).includes(term))).sort((a,b)=>Number(normalize(b.textContent).startsWith(term))-Number(normalize(a.textContent).startsWith(term)));
  list.replaceChildren();active=-1;input.removeAttribute('aria-activedescendant');
  for(const [index,option] of options.entries()){
   const item=document.createElement('div');item.id=list.id+'-'+index;item.setAttribute('role','option');item.setAttribute('aria-selected','false');item.textContent=option.textContent;item.onpointerdown=e=>{e.preventDefault();choose(option)};list.append(item)
  }
  if(!options.length){const empty=document.createElement('p');empty.textContent='Нет подходящих вариантов';empty.className='muted';list.append(empty)}
  list.hidden=false;input.setAttribute('aria-expanded','true')
 }
 input.onfocus=()=>{show();input.select()};input.onclick=()=>{if(list.hidden)show()};input.oninput=()=>show(input.value);
 input.onkeydown=e=>{
  if(e.key==='Escape'){e.preventDefault();close();return}
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();if(list.hidden)show();if(options.length)highlight((active+(e.key==='ArrowDown'?1:-1)+options.length)%options.length);return}
  if(e.key==='Enter'&&!list.hidden){e.preventDefault();if(options.length)choose(options[active<0?0:active])}
 };
 input.onblur=close;select.addEventListener('change',()=>{close();sync()});sync();
 return {sync:()=>{if(list.hidden)sync();else show(input.value)}};
};
})();
