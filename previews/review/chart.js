function renderChart(people){
 const rep=people.find(r=>r.id===(state.sales||state.target))||people[0]||owner(state.target);
 $('target-owner').innerHTML=(people.length?people:reps).map(r=>`<option value="${r.id}">${loc(r.name)}</option>`).join('');
 $('target-owner').value=rep.id;$('target-owner').disabled=!!state.sales;
 const empty=people.length===0;
 $('summary-label').textContent=tr('Orders YTD','年度订单')+' · '+loc(rep.name);
 $('summary-value').textContent=empty?'—':`${money(rep.orders)} / ${money(rep.target)} · ${Math.round(rep.orders/rep.target*100)}%`;
 document.querySelector('.progress i').style.width=empty?'0%':`${rep.orders/rep.target*100}%`;
 $('summary-note').textContent=empty?tr('No records in the selected view','当前范围暂无记录'):tr(`${money(rep.target*.7-rep.orders)} behind individual plan · illustrative figures`,`${money(rep.target*.7-rep.orders)} 低于个人计划 · 演示数值`);
 if(empty){$('chart').innerHTML=`<div class="empty">${tr('No order records · chart area retained','暂无订单记录 · 保留图表区域')}</div>`;return;}
 const x=i=>42+i*45,y=value=>222-value/(Math.ceil(rep.target/10)*10)*192,max=Math.ceil(rep.target/10)*10;
 const values=[.035,.07,.18,.23,.31,.38,.53,.65,1].map(v=>v*rep.orders);
 const points=values.map((v,i)=>`${x(i)},${y(v)}`).join(' ');
 const ticks=Array.from({length:5},(_,i)=>i*max/4);
 const months=state.lang==='en'?['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']:Array.from({length:12},(_,i)=>`${i+1}月`);
 $('chart').innerHTML=`<svg viewBox="0 0 555 260" role="img" aria-label="${tr('Illustrative cumulative orders and individual plan','个人订单累计与计划演示图')}">
 ${ticks.map(v=>`<line x1="42" y1="${y(v)}" x2="537" y2="${y(v)}" stroke="#dce1e5"/><text x="35" y="${y(v)+4}" text-anchor="end">${v}</text>`).join('')}
 <path d="M42 222L537 ${y(rep.target)}V222Z" fill="#ece8df" opacity=".8"/><path d="M42 222L537 ${y(rep.target)}" fill="none" stroke="#78858e" stroke-width="1.5" stroke-dasharray="5 4"/>
 <polyline points="${points}" fill="none" class="actual" stroke-width="2.5"/>
 ${values.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="3.5" fill="white" stroke="#bd6e0a" stroke-width="2"/>`).join('')}
 <line x1="${x(8)}" x2="${x(8)}" y1="22" y2="222" stroke="#bd6e0a"/><text class="now" x="${x(8)}" y="16" text-anchor="middle">${tr('now','当前')}</text>
 ${months.map((m,i)=>`<text x="${x(i)}" y="244" text-anchor="middle">${m}</text>`).join('')}</svg>`;
}
