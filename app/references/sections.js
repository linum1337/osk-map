(()=>{
const permissions=window.CURRENT_USER?.permissions||{};const categories=['cable','closures'].filter(key=>permissions[key==='cable'?'referenceCable':'referenceClosures']);for(const key of ['cable','closures']){document.getElementById('product-'+key).hidden=!categories.includes(key);document.getElementById('reference-'+key).hidden=true}if(!categories.length)return;if(categories.includes('cable')){const script=document.createElement('script');script.src='/references/references.js';document.body.append(script)}if(categories.includes('closures')){const css=document.createElement('link');css.rel='stylesheet';css.href='/references/closures/closures.css';document.head.append(css);const script=document.createElement('script');script.src='/references/closures/closures.js';document.body.append(script)}
function selectCategory(id){
  if(!categories.includes(id))id=categories[0];
  for(const key of categories){
    const selected=key===id;
    const button=document.getElementById('product-'+key);
    button.setAttribute('aria-selected',String(selected));
    button.tabIndex=selected?0:-1;
    document.getElementById('reference-'+key).hidden=!selected;
  }
}
for(const [index,id] of categories.entries()){
  const button=document.getElementById('product-'+id);
  button.addEventListener('click',()=>{location.hash=id;selectCategory(id)});
  button.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const next=event.key==='Home'?0:event.key==='End'?categories.length-1:(index+(event.key==='ArrowRight'?1:-1)+categories.length)%categories.length;
    document.getElementById('product-'+categories[next]).focus();
    location.hash=categories[next];selectCategory(categories[next]);
  });
}
window.addEventListener('hashchange',()=>selectCategory(location.hash.slice(1)));
selectCategory(location.hash.slice(1));
})();
