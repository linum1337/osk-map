(()=>{function mount(){
const section=location.pathname.split('/')[1]||'home';document.documentElement.dataset.section=section;
if(document.getElementById('portal-nav'))return;
const nav=document.createElement('nav');nav.id='portal-nav';nav.setAttribute('aria-label','Разделы рабочего пространства');
const brand=document.createElement('a');brand.href='/';brand.className='portal-brand';brand.setAttribute('aria-label','ОСК — главная страница');const logo=document.createElement('img');logo.src='/assets/osk-logo.png';logo.alt='OSK group';logo.width=92;logo.height=29;brand.append(logo);nav.append(brand);
for(const [href,label,key] of [['/','Главная','home'],['/transport/','Транспортные компании','transport'],['/suppliers/','Поставщики','suppliers'],['/companies/','Компании и таблица','companies'],['/requests/','Запрос в головной офис','requests']]){const a=document.createElement('a');a.href=href;a.textContent=label;if(section===key)a.setAttribute('aria-current','page');nav.append(a)}
const user=window.CURRENT_USER;if(user){const name=document.createElement('span');name.className='portal-user';name.textContent=user.login+' · '+(user.role==='admin'?'Администратор':'Менеджер');nav.append(name)}const change=document.createElement('a');change.href='/login';change.textContent='Сменить пользователя';nav.append(change);document.body.prepend(nav);
const header=document.querySelector('header');if(header){const fit=()=>document.documentElement.style.setProperty('--portal-content-top',Math.ceil(header.getBoundingClientRect().bottom)+'px');fit();new ResizeObserver(fit).observe(header);window.addEventListener('resize',fit)}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();})();
