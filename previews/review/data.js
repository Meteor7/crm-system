// Synthetic records for the standalone UI prototype. No CRM data or API calls.
const reps = [
 {id:'dongbao',name:['Dongbao Xiong','熊东宝'],city:['Shanghai / Wuxi','上海 / 无锡'],region:'East China',market:'Frontend',activity:[5,2,1,2],prior:[4,1,1,1],goals:[6,2,2,2],stages:[12,6,4,3,4,1,4],pipeline:46.2,orders:21.8,target:40},
 {id:'chenmian',name:['ChenMian Yan','演示员工201'],city:['Beijing / Dalian','北京 / 大连'],region:'North China',market:'Frontend',activity:[4,1,1,1],prior:[3,1,0,1],goals:[5,2,1,2],stages:[10,7,4,3,4,1,2],pipeline:31.8,orders:14.5,target:30},
 {id:'ruifeng',name:['Ruifeng Luo','罗瑞峰'],city:['Beijing / Shenzhen','北京 / 深圳'],region:'South China',market:'Advanced Packaging',activity:[3,1,1,1],prior:[2,0,1,1],goals:[4,1,1,1],stages:[9,5,4,4,3,1,2],pipeline:24.6,orders:12,target:25},
 {id:'xiaolan',name:['Xiaolan Qiu','邱晓岚'],city:["Xi’an / Chengdu",'西安 / 成都'],region:'West China',market:'Advanced Packaging',activity:[2,0,0,1],prior:[2,0,1,0],goals:[3,1,1,1],stages:[7,4,3,2,3,0,1],pipeline:18.9,orders:13.2,target:28}
];
const regions = [['East China','华东'],['South China','华南'],['West China','华西'],['North China','华北'],['Central China','华中']];
const stageNames = [['Qualified opportunity','合格商机'],['Demo done','Demo 完成'],['Customer budget approved','客户预算批准'],['RFQ validated','RFQ 确认'],['Quotation sent','报价已发出'],['Internal validation','内部验证'],['PO received (YTD)','已收到 PO（年累计）']];
const activityNames = [['Customer visits','客户沟通'],['New qualified leads','新增合格线索'],['Test runs completed','完成测试'],['Quotes first published','首次发布报价']];
const notes = [['Completed customer conversations','已完成的客户沟通'],['Anchored to Lead conversion time','以线索转化时间为准'],['Completed Test Runs only','仅统计已完成测试'],['First published quotation versions','仅统计首次发布版本']];
const stalled = [
 {id:'stall1',customer:'HuaXin Fab 2',owner:'dongbao',stage:4,value:8.2,days:42,note:['Budget review pushed to Q4','预算评审推迟到 Q4']},
 {id:'stall2',customer:'NovaSi Semiconductor',owner:'ruifeng',stage:0,value:null,days:35,note:['Waiting for customer wafers','等待客户样片']},
 {id:'stall3',customer:'Dongfang Micro',owner:'chenmian',stage:4,value:4.1,days:28,note:['Competitor re-quoted lower','竞争对手调整报价']},
 {id:'stall4',customer:'Kunpeng Advanced Pkg',owner:'xiaolan',stage:5,value:6.8,days:21,note:['Build launched · PO pending on payment terms','已启动生产 · PO 等待付款条款确认']}
];
const losses = [
 {id:'loss1',customer:'Qinghe Semiconductor',owner:'dongbao',stage:4,value:5.2,date:'2026-08-28',note:['Customer moved the capital budget to next year.','客户将资本支出预算推迟至明年。']},
 {id:'loss2',customer:'SinoChip Packaging',owner:'ruifeng',stage:3,value:3.4,date:'2026-08-13',note:['The current tool configuration did not meet throughput requirements.','当前设备配置未达到客户产能要求。']},
 {id:'loss3',customer:'Jingwei Micro',owner:'chenmian',stage:2,value:2.8,date:'2026-07-21',note:['Customer selected the incumbent supplier after evaluation.','客户评估后选择了现有供应商。']},
 {id:'loss4',customer:'Westlake Devices',owner:'xiaolan',stage:4,value:4.6,date:'2026-06-09',note:['Project stopped after the customer changed its process roadmap.','客户调整工艺路线后终止了该项目。']}
];
const state={lang:'en',region:'',sales:'',market:'',period:'week',offset:0,mode:'count',empty:false,target:'dongbao'};
const $ = id => document.getElementById(id);
const tr = (en,zh) => state.lang==='en'?en:zh;
const loc = pair => state.lang==='en'?pair[0]:pair[1];
const money = value => value==null?'—':`¥${Number(value.toFixed(1))}M`;
const filtered = () => state.empty?[]:reps.filter(r=>(!state.region||r.region===state.region)&&(!state.sales||r.id===state.sales)&&(!state.market||r.market===state.market));
const owner = id => reps.find(r=>r.id===id);
const factor = () => ({week:1,month:4,quarter:12,year:36}[state.period]);
const inScope = (rows,people) => rows.filter(r=>people.some(p=>p.id===r.owner));
function periodInfo(){
 const date=new Date(Date.UTC(2026,8,7));
 if(state.period==='week')date.setUTCDate(date.getUTCDate()+state.offset*7);
 else {date.setUTCDate(1);date.setUTCMonth((state.period==='year'?0:state.period==='quarter'?6:8)+state.offset*({month:1,quarter:3,year:12}[state.period]));}
 const end=new Date(date);if(state.period==='week')end.setUTCDate(end.getUTCDate()+6);else {end.setUTCMonth(end.getUTCMonth()+({month:1,quarter:3,year:12}[state.period]));end.setUTCDate(0);}
 const startYear=new Date(Date.UTC(date.getUTCFullYear(),0,1));
 const week=Math.ceil((((date-startYear)/86400000)+startYear.getUTCDay())/7);
 const title=state.period==='week'?tr(`Week ${week}`,`第 ${week} 周`):state.period==='quarter'?`Q${Math.floor(date.getUTCMonth()/3)+1}`:date.toLocaleDateString(state.lang==='en'?'en-US':'zh-CN',{timeZone:'UTC',year:'numeric',...(state.period==='month'?{month:'long'}:{})});
 return {title,short:state.period==='week'?`W${week} · ${date.getUTCFullYear()}`:title,date:`${date.toLocaleDateString(state.lang==='en'?'en-US':'zh-CN',{timeZone:'UTC',month:'short',day:'numeric'})} – ${end.toLocaleDateString(state.lang==='en'?'en-US':'zh-CN',{timeZone:'UTC',month:'short',day:'numeric',year:'numeric'})}`};
}
