(()=>{function mount(){
const section=location.pathname.split('/')[1]||'home';document.documentElement.dataset.section=section;
if(document.getElementById('portal-nav'))return;
const nav=document.createElement('nav');nav.id='portal-nav';nav.setAttribute('aria-label','Разделы рабочего пространства');
for(const [href,label,key] of [['/','Главная','home'],['/transport/','Транспортные компании','transport'],['/suppliers/','Поставщики','suppliers'],['/companies/','Компании и таблица','companies']]){const a=document.createElement('a');a.href=href;a.textContent=label;if(section===key)a.setAttribute('aria-current','page');nav.append(a)}
const user=window.CURRENT_USER;if(user){const name=document.createElement('span');name.className='portal-user';name.textContent=user.login+' · '+(user.role==='admin'?'Администратор':'Менеджер');nav.append(name)}document.body.prepend(nav);
const header=document.querySelector('header');if(header){const fit=()=>document.documentElement.style.setProperty('--portal-content-top',Math.ceil(header.getBoundingClientRect().bottom)+'px');fit();new ResizeObserver(fit).observe(header);window.addEventListener('resize',fit)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();})();
