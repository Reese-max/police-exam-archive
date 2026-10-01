/* Generated Analytics code/data pair（自動產生，勿手改）SHA-256: 8e936f8d815766525f6f726295425aa7ff7d42380328a4c916b205ad194b9590 */
/* ===== 真實資料（由 analytics.json 自動產生，勿手改） ===== */
const STATS = {"total":42518,"choice":36760,"essay":5758,"categories":49,"subjects":101,"firstYear":106,"lastYear":115,"yearCount":10};
const YEARS = ["106","107","108","109","110","111","112","113","114","115"];
const CATEGORIES = [{"id":"c0","name":"國境警察學系移民組","total":3186,"year":[424,422,424,285,333,330,285,353,330,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c1","name":"行政警察學系","total":2042,"year":[205,205,205,205,204,205,203,204,203,203],"donut":[21.5,26.3,25.5,26.6]},{"id":"c2","name":"行政警察","total":1844,"year":[205,205,210,205,204,205,203,204,203,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c3","name":"刑事警察學系","total":1689,"year":[182,182,182,182,181,182,181,179,180,58],"donut":[21.5,26.3,25.5,26.6]},{"id":"c4","name":"刑事警察","total":1636,"year":[182,182,187,182,181,182,181,179,180,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c5","name":"鑑識科學學系","total":1490,"year":[159,159,158,160,159,159,158,158,158,62],"donut":[21.5,26.3,25.5,26.6]},{"id":"c6","name":"行政管理學系","total":1460,"year":[159,159,158,159,158,159,158,158,157,35],"donut":[21.5,26.3,25.5,26.6]},{"id":"c7","name":"鑑識科學","total":1433,"year":[159,159,163,160,159,159,158,158,158,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c8","name":"行政管理","total":1430,"year":[159,159,163,159,158,159,158,158,157,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c9","name":"法律學系","total":1423,"year":[155,155,155,155,154,155,154,154,153,33],"donut":[21.5,26.3,25.5,26.6]},{"id":"c10","name":"警察法制","total":1395,"year":[155,155,160,155,154,155,154,154,153,0],"donut":[21.5,26.3,25.5,26.6]},{"id":"c11","name":"公共安全學系社安組","total":1231,"year":[136,136,136,136,135,136,135,135,134,12],"donut":[21.5,26.3,25.5,26.6]},{"id":"c12","name":"國境警察學系境管組","total":1231,"year":[136,136,136,136,135,136,135,135,134,12],"donut":[21.5,26.3,25.5,26.6]},{"id":"c13","name":"犯罪防治學系預防組","total":1231,"year":[136,136,136,136,135,136,135,135,134,12],"donut":[21.5,26.3,25.5,26.6]},{"id":"c14","name":"公共安全","total":1224,"year":[136,136,141,136,135,136,135,135,134,0],"donut":[21.5,26.3,25.5,26.6]}];
const ALL_YEAR = [4571,4844,4668,4746,4766,4793,4446,4509,4468,707];
const ALL_DONUT = [21.5,26.3,25.5,26.6];
const KEYWORDS = [["警察",8414],["犯罪",3727],["司法院大法官",3518],["憲法",2965],["派出所",2293],["勤務",2248],["偵查",1932],["憲法增修條",1393],["毒品",1108],["搜索",1088],["社會秩序維護法",1083],["消防",1003],["分局",995],["行政執行",941],["警察職權行使法",890],["逮捕",543],["基本權利",542],["詢問",526],["警察法",521],["行政執行法",511],["人口販運",482],["巡邏勤",456],["移民",453],["鑑識",452],["災害",440],["交通事故",422],["救護",398],["人身自由",394],["國家賠償",356],["指紋",353],["詐欺",337],["集會遊行法",319],["刑法",314],["地方自治",304],["警械使用條例",290],["訴訟權",284],["警政署",284],["扣押",276],["臨檢",268],["搜索票",261],["行政處分",254],["刑事訴訟法",248],["公務人員行政中立法",247],["跟蹤",234],["拘提",223],["DNA",223],["竊盜",222],["酒駕",222],["盤查",220],["傷害",208]];
const TREND_CATS = ["c0","c1","c2","c3","c4"];
/* ===== 出題趨勢分析 App ===== */
(function(){
  const charts = {};
  let currentCat = 'all';

  // 讀取目前主題的 CSS 變數做為圖表配色
  function pal(){
    const cs = getComputedStyle(document.documentElement);
    const v = n => cs.getPropertyValue(n).trim();
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
      primary: v('--primary'),
      grid: v('--grid-line'),
      text: v('--chart-text'),
      card: v('--card'),
      border: v('--border'),
      // 綠色系 + 暖色點綴
      greens: dark
        ? ['#7db892','#5e9b76','#4a7c5e','#9ccfac','#3d6b50']
        : ['#4a7c5e','#6b9e7f','#8fbfa0','#b5d9c2','#cfe5d6'],
      warm: dark ? '#cdab73' : '#c9a66b',
      // 答案分佈 A B C D
      donut: dark
        ? ['#7db892','#5e9b76','#cdab73','#4a7c5e']
        : ['#4a7c5e','#8fbfa0','#c9a66b','#b5d9c2'],
      tooltipBg: dark ? '#34322b' : '#2d2a26',
    };
  }

  // ===== Chart.js 全域樣式 =====
  function applyDefaults(p){
    Chart.defaults.font.family = "'Noto Sans TC', sans-serif";
    Chart.defaults.font.size = 12.5;
    Chart.defaults.font.weight = '500';
    Chart.defaults.color = p.text;
  }

  const tooltipBase = p => ({
    backgroundColor: p.tooltipBg,
    titleColor:'#fff', bodyColor:'#fff',
    padding:12, cornerRadius:9, displayColors:true, boxPadding:4,
    titleFont:{weight:'700',size:13}, bodyFont:{weight:'600',size:12.5},
    borderColor:'rgba(255,255,255,.08)', borderWidth:1,
  });

  // 取得目前資料集（依篩選）
  function dataFor(){
    if(currentCat === 'all'){
      return { year: ALL_YEAR, donut: ALL_DONUT, total: STATS.total };
    }
    const c = CATEGORIES.find(x=>x.id===currentCat);
    return { year: c.year, donut: c.donut, total: c.total };
  }

  // ===== 各年度出題數（長條） =====
  function buildYear(p){
    const d = dataFor();
    charts.year = new Chart(document.getElementById('yearChart'), {
      type:'bar',
      data:{ labels: YEARS.map(y=>y+' 年'),
        datasets:[{ data:d.year, backgroundColor:p.greens[0], hoverBackgroundColor:p.greens[1],
          borderRadius:7, borderSkipped:false, maxBarThickness:42 }] },
      options:{ responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{display:false}, tooltip:{...tooltipBase(p),
          callbacks:{ label:c=>'  '+c.parsed.y.toLocaleString()+' 題' } } },
        scales:{
          x:{ grid:{display:false}, border:{display:false}, ticks:{color:p.text,font:{weight:'600'}} },
          y:{ grid:{color:p.grid,drawTicks:false}, border:{display:false},
            ticks:{color:p.text,padding:8,callback:v=>v>=1000?(v/1000)+'k':v}, beginAtZero:true } },
        animation:{duration:900,easing:'easeOutQuart'} }
    });
  }

  // ===== 答案分佈（甜甜圈） =====
  function buildDonut(p){
    const d = dataFor();
    charts.donut = new Chart(document.getElementById('donutChart'), {
      type:'doughnut',
      data:{ labels:['A','B','C','D'],
        datasets:[{ data:d.donut, backgroundColor:p.donut,
          borderColor:p.card, borderWidth:3, hoverOffset:8 }] },
      options:{ responsive:true, maintainAspectRatio:false, cutout:'66%',
        plugins:{ legend:{display:false}, tooltip:{...tooltipBase(p),
          callbacks:{ label:c=>'  '+c.label+'：'+c.parsed+'%' } } },
        animation:{duration:900,animateRotate:true} }
    });
    // 自訂圖例
    const labels=['A','B','C','D'];
    document.getElementById('donutLegend').innerHTML = labels.map((l,i)=>
      `<span class="li"><span class="sw" style="background:${p.donut[i]}"></span>${l}　${d.donut[i]}%</span>`
    ).join('');
  }

  // ===== 各類科題目數（水平長條） =====
  function buildCat(p){
    const sorted = [...CATEGORIES].sort((a,b)=>b.total-a.total);
    const colors = sorted.map((_,i)=>{
      const g = p.greens; return g[Math.min(i,g.length-1)] || (i%2 ? p.warm : g[2]);
    });
    // 漸層綠：前段深、後段淺，最後兩條用暖色點綴
    const palette = sorted.map((_,i)=>{
      if(i>=sorted.length-2) return p.warm;
      const g=p.greens; return g[Math.min(i, g.length-1)];
    });
    charts.cat = new Chart(document.getElementById('catChart'), {
      type:'bar',
      data:{ labels:sorted.map(c=>c.name),
        datasets:[{ data:sorted.map(c=>c.total), backgroundColor:palette,
          borderRadius:6, borderSkipped:false, maxBarThickness:26 }] },
      options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{display:false}, tooltip:{...tooltipBase(p),
          callbacks:{ label:c=>'  '+c.parsed.x.toLocaleString()+' 題' } } },
        scales:{
          x:{ grid:{color:p.grid,drawTicks:false}, border:{display:false},
            ticks:{color:p.text,callback:v=>v>=1000?(v/1000)+'k':v}, beginAtZero:true },
          y:{ grid:{display:false}, border:{display:false},
            ticks:{color:p.text,font:{weight:'600',size:13}} } },
        animation:{duration:900,easing:'easeOutQuart'} }
    });
  }

  // ===== 各類科歷年趨勢（多線折線） =====
  function buildTrend(p){
    const cats = TREND_CATS.map(id=>CATEGORIES.find(c=>c.id===id));
    const colorset = [p.greens[0], p.greens[1], p.warm, p.greens[3], p.greens[2]];
    charts.trend = new Chart(document.getElementById('trendChart'), {
      type:'line',
      data:{ labels:YEARS.map(y=>y+' 年'),
        datasets:cats.map((c,i)=>({
          label:c.name, data:c.year, borderColor:colorset[i],
          backgroundColor:colorset[i], borderWidth:2.5, tension:.38,
          pointRadius:3, pointHoverRadius:6, pointBackgroundColor:colorset[i],
          pointBorderColor:p.card, pointBorderWidth:2, fill:false })) },
      options:{ responsive:true, maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{ legend:{position:'top',align:'end',
            labels:{usePointStyle:true,pointStyleWidth:10,boxHeight:7,padding:16,
              color:p.text,font:{weight:'600',size:12.5}} },
          tooltip:{...tooltipBase(p), callbacks:{label:c=>'  '+c.dataset.label+'：'+c.parsed.y+' 題'}} },
        scales:{
          x:{ grid:{display:false}, border:{display:false}, ticks:{color:p.text,font:{weight:'600'}} },
          y:{ grid:{color:p.grid,drawTicks:false}, border:{display:false},
            ticks:{color:p.text,padding:8}, beginAtZero:false } },
        animation:{duration:1000,easing:'easeOutQuart'} }
    });
  }

  function buildAll(){
    const p = pal();
    applyDefaults(p);
    Object.values(charts).forEach(c=>c&&c.destroy());
    buildYear(p); buildDonut(p); buildCat(p); buildTrend(p);
  }

  // ===== 關鍵字 Top 50 =====
  function renderKeywords(){
    const max = KEYWORDS[0][1];
    const greens = pal().greens;
    document.getElementById('kwGrid').innerHTML = KEYWORDS.map((k,i)=>{
      const pct = (k[1]/max*100).toFixed(1);
      const top = i<3;
      const color = i<3 ? greens[0] : i<10 ? greens[1] : i<25 ? greens[2] : greens[3];
      return `<div class="kw-row${top?' top':''}">
        <span class="kw-rank">${i+1}</span>
        <span class="kw-name" title="${k[0]}">${k[0]}</span>
        <span class="kw-bar-track"><span class="kw-bar-fill" data-pct="${pct}" style="background:${color}"></span></span>
        <span class="kw-count">${k[1].toLocaleString()}</span>
      </div>`;
    }).join('');
  }
  function animateKeywords(){
    document.querySelectorAll('.kw-bar-fill').forEach(el=>{
      el.style.width = el.dataset.pct + '%';
    });
  }
  function recolorKeywords(){
    const greens = pal().greens;
    document.querySelectorAll('.kw-bar-fill').forEach((el,i)=>{
      el.style.background = i<3 ? greens[0] : i<10 ? greens[1] : i<25 ? greens[2] : greens[3];
    });
  }

  // ===== 統計卡（直接呈現，不做 count-up 動畫）=====
  function countUp(){
    document.querySelectorAll('.num[data-target]').forEach(el=>{
      el.textContent = (+el.dataset.target).toLocaleString();
    });
  }

  // ===== 篩選 =====
  function setupFilter(){
    const sel = document.getElementById('catSelect');
    CATEGORIES.forEach(c=>{
      const o=document.createElement('option'); o.value=c.id; o.textContent=c.name; sel.appendChild(o);
    });
    sel.addEventListener('change', ()=>{
      currentCat = sel.value;
      const tag = document.getElementById('filterTag');
      const d = dataFor();
      const name = currentCat==='all' ? '全部類科' : CATEGORIES.find(c=>c.id===currentCat).name;
      tag.textContent = name + ' · ' + d.total.toLocaleString() + ' 題';
      // 只重建受篩選影響的兩張圖
      const p=pal();
      charts.year.destroy(); buildYear(p);
      charts.donut.destroy(); buildDonut(p);
    });
  }

  // ===== 主題切換 =====
  function setupTheme(){
    const btn = document.getElementById('themeToggle');
    const label = document.getElementById('themeLabel');
    function apply(dark){
      document.documentElement.setAttribute('data-theme', dark?'dark':'light');
      label.textContent = dark ? '淺色模式' : '深色模式';
      try{localStorage.setItem('exam-dark', dark);}catch(e){}
    }
    let saved=null; try{saved=localStorage.getItem('exam-dark');}catch(e){}
    apply(saved==='true'||(saved===null&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches));
    btn.addEventListener('click', ()=>{
      const next = document.documentElement.getAttribute('data-theme')!=='dark';
      apply(next);
      setTimeout(()=>{ buildAll(); recolorKeywords(); }, 60);
    });
  }

  // ===== Init =====
  function init(){
    setupTheme();
    setupFilter();
    buildAll();
    renderKeywords();
    countUp();
    setTimeout(animateKeywords, 300);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
