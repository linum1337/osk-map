(()=>{const next=document.querySelector('input[name=next]');if(next&&location.hash&&!next.value.includes('#'))next.value+=location.hash;})();
