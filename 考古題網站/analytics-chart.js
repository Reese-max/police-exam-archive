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
      return { year: ALL_YEAR, donut: ALL_DONUT, total: 41811 };
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
