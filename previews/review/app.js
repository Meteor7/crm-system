function showDetails(title,rows){
 $('detail-title').textContent=title;
 $('detail-content').innerHTML=rows.length?rows.map(r=>`<article class="loss-row"><div><strong>${r.customer}</strong><p>${loc(r.note)}</p><small>${loc(owner(r.owner).name)} · ${loc(stageNames[r.stage])}</small></div><span>${money(r.value)}</span></article>`).join(''):`<div class="empty">${tr('No records in this view','当前范围暂无记录')}</div>`;
 $('detail-dialog').showModal();
}
['region','sales','market'].forEach(id=>$(id).addEventListener('change',e=>{state[id]=e.target.value;render()}));
$('target-owner').addEventListener('change',e=>{state.target=e.target.value;render()});
$('language').addEventListener('click',()=>{state.lang=state.lang==='en'?'zh':'en';render()});
$('empty-toggle').addEventListener('click',()=>{state.empty=!state.empty;render()});
$('prev').addEventListener('click',()=>{state.offset--;render()});
$('next').addEventListener('click',()=>{state.offset++;render()});
$('close-dialog').addEventListener('click',()=>$('detail-dialog').close());
document.addEventListener('click',event=>{
 const button=event.target.closest('button');if(!button)return;
 if(button.dataset.period){state.period=button.dataset.period;state.offset=0;render()}
 if(button.dataset.mode){state.mode=button.dataset.mode;render()}
 if(button.dataset.rep){state.sales=button.dataset.rep;render()}
 if(button.dataset.record){const record=[...stalled,...losses].find(r=>r.id===button.dataset.record);showDetails(record.customer,[record])}
 if(button.dataset.detail){const isLoss=button.dataset.detail==='losses';showDetails(isLoss?tr('Recorded losses','丢单记录'):tr('Warning details','预警明细'),inScope(isLoss?losses:stalled,filtered()))}
 if(button.dataset.stage!==undefined){const stage=Number(button.dataset.stage);showDetails(loc(stageNames[stage]),inScope([...stalled,...losses],filtered()).filter(r=>r.stage===stage))}
 if(button.dataset.activity!==undefined){const index=Number(button.dataset.activity);showDetails(loc(activityNames[index]),inScope(stalled,filtered()).map(r=>({...r,note:notes[index]})))}
});
render();
