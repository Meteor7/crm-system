function render(){
 document.documentElement.lang=state.lang==='en'?'en':'zh-CN';
 document.querySelectorAll('[data-en]').forEach(e=>e.textContent=e.dataset[state.lang==='en'?'en':'zh']);
 const people=filtered(),rows=inScope(stalled,people),lost=inScope(losses,people),p=periodInfo();
 $('period-title').textContent=p.title;$('period-date').textContent=p.date;$('date-label').textContent=p.short;$('review-tab').textContent=`Review · ${p.short.split(' · ')[0]}`;
 $('activity-heading').textContent=({week:tr('Weekly activity','周度活动'),month:tr('Monthly activity','月度活动'),quarter:tr('Quarterly activity','季度活动'),year:tr('Annual activity','年度活动')})[state.period];
 $('region').innerHTML=`<option value="">${tr('All regions','全部区域')}</option>`+regions.map(r=>`<option value="${r[0]}">${loc(r)}</option>`).join('');$('region').value=state.region;
 $('sales').innerHTML=`<option value="">${tr('All (4)','全部 (4)')}</option>`+reps.map(r=>`<option value="${r.id}">${loc(r.name)}</option>`).join('');$('sales').value=state.sales;
 $('market').innerHTML=`<option value="">${tr('All markets','全部市场')}</option><option>Frontend</option><option>Advanced Packaging</option>`;$('market').value=state.market;
 $('language').textContent=tr('中文','English');$('empty-toggle').textContent=state.empty?tr('Show sample data','显示演示数据'):tr('Empty state','查看空状态');
 document.querySelectorAll('[data-period]').forEach(b=>{b.classList.toggle('active',b.dataset.period===state.period);b.setAttribute('aria-pressed',b.dataset.period===state.period)});
 document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===state.mode);b.setAttribute('aria-pressed',b.dataset.mode===state.mode)});
 const warningCount=rows.length+Math.min(people.length,2)+Math.min(people.length,3);
 $('warning-title').textContent=tr(`Warnings · ${warningCount} items need attention`,`预警 · ${warningCount} 项需关注`);
 $('warning-description').textContent=tr(`${Math.min(people.length,3)} opportunities lost · ${rows.length} overdue actions · ${Math.min(people.length,2)} downgrades`,`${Math.min(people.length,3)} 个丢单 · ${rows.length} 项行动逾期 · ${Math.min(people.length,2)} 次概率降档`);
 $('activities').innerHTML=activityNames.map((name,i)=>{const n=people.reduce((a,r)=>a+r.activity[i]*factor(),0),prev=people.reduce((a,r)=>a+r.prior[i]*factor(),0),delta=n-prev,target=state.sales&&people.length?owner(state.sales).goals[i]*factor():null;return `<article class="activity-item"><button class="activity-label" data-activity="${i}">${loc(name)}</button><div class="activity-value"><strong>${n}</strong>${target===null?'':`<span>/ ${target} ${tr('target','目标')}</span>`}</div><p class="trend ${delta<0?'down':''}">${delta===0?tr('— flat','— 持平'):`${delta>0?'▲':'▼'} ${Math.abs(delta)} ${tr('vs prior period','较上期')}`}</p><p class="subtle">${loc(notes[i])}</p></article>`}).join('');
 const total=people.reduce((s,r)=>s+r.pipeline,0),counts=stageNames.map((_,i)=>people.reduce((a,r)=>a+r.stages[i],0));
 $('pipeline-intro').textContent=tr(`Open pipeline ${money(total)} across stages 2–6 (qualified opportunities carry no value).`,`S2–S6 在途商机 ${money(total)}；合格商机阶段仅统计数量。`);
 const values=counts.map((n,i)=>i===0?0:i===6?people.reduce((s,r)=>s+r.orders,0):total*[0,.32,.25,.18,.2,.05][i]);
 const max=Math.max(1,...(state.mode==='count'?counts:values));
 $('stages').innerHTML=stageNames.map((name,i)=>`<button class="stage" data-stage="${i}"><span class="stage-label">${i+1}. ${loc(name)}${i===5?`<small>${tr('optional · before PO','可选 · PO 前提前生产')}</small>`:''}</span><span class="bar"><i style="width:${(state.mode==='count'?counts[i]:values[i])/max*100}%"></i></span><span class="stage-value"><strong>${counts[i]}</strong> ${tr('deals','个')}<small>${i===0?tr('no value yet','仅计数量'):money(values[i])}</small></span></button>`).join('');
 $('rep-head').innerHTML='<tr>'+[tr('Rep','销售'),tr('Visits','沟通'),tr('Leads','线索'),tr('Tests','测试'),tr('Quotes','报价'),'Pipeline',tr('PO YTD','PO 年累计')].map(t=>`<th>${t}</th>`).join('')+'</tr>';
 $('rep-body').innerHTML=people.map(r=>`<tr><td><button class="row-button" data-rep="${r.id}">${loc(r.name)}</button><small>${loc(r.city)}</small></td>${r.activity.map(n=>`<td class="numeric">${n*factor()}</td>`).join('')}<td class="numeric">${money(r.pipeline)}</td><td class="numeric">${r.stages[6]}</td></tr>`).join('');$('rep-empty').hidden=people.length>0;
 $('stalled-head').innerHTML='<tr>'+[tr('Customer','客户'),tr('Stage','阶段'),tr('Value','金额'),tr('Idle','停滞'),tr('Owner','销售')].map(t=>`<th>${t}</th>`).join('')+'</tr>';
 $('stalled-body').innerHTML=rows.map(r=>`<tr><td><button class="row-button" data-record="${r.id}">${r.customer}</button><small>${loc(r.note)}</small></td><td>${r.stage+1}. ${loc(stageNames[r.stage])}</td><td class="numeric">${money(r.value)}</td><td class="idle ${r.days<35?'amber':''}">${Math.floor(r.days/7)}<br>${tr('wk','周')}</td><td>${loc(owner(r.owner).name)}</td></tr>`).join('');$('stalled-empty').hidden=rows.length>0;
 $('loss-list').innerHTML=lost.map(r=>`<article class="loss-row"><div><button class="row-button" data-record="${r.id}">${r.customer}</button><p>${loc(r.note)}</p><small>${loc(owner(r.owner).name)} · ${r.date} · ${loc(stageNames[r.stage])}</small></div><span class="loss-value">${money(r.value)}</span></article>`).join('');$('loss-empty').hidden=lost.length>0;
 $('loss-total').textContent=tr(`${lost.length} recorded losses · original reasons`,`${lost.length} 条丢单记录 · 保留原始原因`);
 renderChart(people);
}
