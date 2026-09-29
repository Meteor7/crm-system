// Static shell preview only. Production Review reuses src/app/AppShell.vue.
const previewShell = document.getElementById('preview-shell');
const previewSidebar = document.getElementById('app-sidebar');
function closePreviewNavigation(){
 previewSidebar.classList.remove('is-open');
 document.getElementById('nav-scrim').hidden=true;
 document.getElementById('mobile-nav').setAttribute('aria-expanded','false');
}
document.getElementById('collapse-nav').onclick=()=>{
 previewShell.classList.add('is-sidebar-collapsed');previewSidebar.inert=true;
 document.getElementById('expand-nav').focus();
};
document.getElementById('expand-nav').onclick=()=>{
 previewShell.classList.remove('is-sidebar-collapsed');previewSidebar.inert=false;
 document.getElementById('collapse-nav').focus();
};
document.getElementById('mobile-nav').onclick=()=>{
 previewShell.classList.remove('is-sidebar-collapsed');previewSidebar.inert=false;
 previewSidebar.classList.add('is-open');document.getElementById('nav-scrim').hidden=false;
 document.getElementById('mobile-nav').setAttribute('aria-expanded','true');
 document.getElementById('close-nav').focus();
};
['close-nav','nav-scrim'].forEach(id=>document.getElementById(id).onclick=()=>{closePreviewNavigation();document.getElementById('mobile-nav').focus()});
document.addEventListener('keydown',event=>{if(event.key==='Escape' && previewSidebar.classList.contains('is-open')){closePreviewNavigation();document.getElementById('mobile-nav').focus()}});
document.getElementById('shell-language').onclick=()=>document.getElementById('language').click();
window.matchMedia('(max-width:839px)').addEventListener('change',()=>{closePreviewNavigation();previewShell.classList.remove('is-sidebar-collapsed');previewSidebar.inert=false});
