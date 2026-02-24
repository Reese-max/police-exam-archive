/* === 共用功能（靜態網站 — 所有資料來自可信的本地 JSON）=== */
function debounce(fn, ms) {
  let t; return function(...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); };
}
const debouncedSearch = debounce(v => doSearch(v), window.innerWidth <= 768 ? 300 : 180);
function toggleYear(el) { el.classList.toggle('active'); el.setAttribute('aria-expanded', el.classList.contains('active') ? 'true' : 'false'); }

function clearHighlights() {
  document.querySelectorAll('.highlight').forEach(h => {
    const p = h.parentNode;
    p.replaceChild(document.createTextNode(h.textContent), h);
    p.normalize();
  });
}
function highlightText(node, query) {
  if (!query) return 0;
  if (node.nodeType === 3) {
    var count = 0;
    var current = node;
    var lowerQuery = query.toLowerCase();
    while (current) {
      var idx = current.textContent.toLowerCase().indexOf(lowerQuery);
      if (idx === -1) break;
      var span = document.createElement('span');
      span.className = 'highlight';
      var matched = current.splitText(idx);
      current = matched.splitText(query.length);
      span.appendChild(matched.cloneNode(true));
      matched.parentNode.replaceChild(span, matched);
      count++;
    }
    return count;
  } else if (node.nodeType === 1 && node.childNodes.length && !/(script|style)/i.test(node.tagName) && !node.classList.contains('highlight')) {
    let c = 0;
    for (let i = 0; i < node.childNodes.length; i++) c += highlightText(node.childNodes[i], query);
    return c;
  }
  return 0;
}

let activeYearFilter = '';
function toggleFilter(el, type) {
  if (type === 'year') {
    document.querySelectorAll('.filter-chip[data-year]').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    activeYearFilter = el.dataset.year || '';
    doSearch(document.getElementById('searchInput').value);
  }
}

let searchHits = [];
let currentHitIdx = -1;
let currentView = 'year';

function getActiveViewSelector() { return currentView === 'subject' ? '#subjectView' : '#yearView'; }

function doSearch(query) {
  if (query === undefined || query === null) query = document.getElementById('searchInput').value || '';
  query = query.trim();
  const stats = document.getElementById('searchStatsText');
  const vs = getActiveViewSelector();
  const cards = document.querySelectorAll(vs + ' .subject-card');
  const sections = document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section');
  clearHighlights();
  searchHits = [];
  currentHitIdx = -1;
  const bmFilter = bookmarkFilterActive;
  const bmarks = bmFilter ? getStore('exam-bookmarks') : null;

  if (activeYearFilter && !query.trim()) {
    if (currentView === 'subject') {
      cards.forEach(function(c) {
        if (bmFilter) { const cid = c.getAttribute('data-card-id') || c.id; if (!bmarks[cid]) { c.style.display = 'none'; return; } }
        const tag = c.querySelector('.sv-year-tag');
        c.style.display = (tag && tag.textContent.trim().startsWith(activeYearFilter)) ? '' : 'none';
      });
      sections.forEach(function(s) {
        s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
      });
    } else {
      sections.forEach(s => {
        const h = s.querySelector('.year-heading');
        const yName = h ? h.textContent.trim() : '';
        s.style.display = yName.startsWith(activeYearFilter) ? '' : 'none';
      });
      cards.forEach(c => {
        if (bmFilter) { const cid = c.getAttribute('data-card-id') || c.id; if (!bmarks[cid]) { c.style.display = 'none'; return; } }
        c.style.display = '';
      });
    }
    stats.textContent = activeYearFilter ? '篩選：' + activeYearFilter + '年' : '';
    updateSearchJump();
    return;
  }
  if (!query.trim() && !activeYearFilter && !bmFilter) {
    cards.forEach(c => { c.style.display = ''; c.classList.remove('open'); });
    sections.forEach(s => s.style.display = '');
    stats.textContent = '';
    updateSearchJump();
    return;
  }
  let matchCount = 0, totalHL = 0;
  cards.forEach(card => {
    if (bmFilter) {
      const cid = card.getAttribute('data-card-id') || card.id;
      if (!bmarks[cid]) { card.style.display = 'none'; return; }
    }
    if (activeYearFilter) {
      if (currentView === 'subject') {
        const tag = card.querySelector('.sv-year-tag');
        if (!tag || !tag.textContent.trim().startsWith(activeYearFilter)) { card.style.display = 'none'; return; }
      } else {
        const yearSection = card.closest('.year-section');
        const yName = yearSection ? yearSection.querySelector('.year-heading').textContent.trim() : '';
        if (!yName.startsWith(activeYearFilter)) { card.style.display = 'none'; return; }
      }
    }
    const text = (window._cardTextCache && window._cardTextCache.has(card)) ? window._cardTextCache.get(card) : card.textContent.toLowerCase();
    const queryLower = query.toLowerCase();
    if (!query.trim() || text.includes(queryLower)) {
      card.style.display = '';
      if (query.trim()) {
        card.classList.add('open');
        const body = card.querySelector('.subject-body');
        if (body) totalHL += highlightText(body, query);
      }
      matchCount++;
    } else {
      card.style.display = 'none'; card.classList.remove('open');
    }
  });
  sections.forEach(s => {
    s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
  });
  searchHits = Array.from(document.querySelectorAll(vs + ' .highlight'));
  let txt = '';
  if (query.trim()) txt += '找到 ' + matchCount + ' 份相關試卷，' + totalHL + ' 處匹配';
  else if (activeYearFilter) txt += '篩選：' + activeYearFilter + '年，' + matchCount + ' 份試卷';
  stats.textContent = txt;
  updateSearchJump();
}

/* === 搜尋跳轉 (Phase 4) === */
function updateSearchJump() {
  const jumpEl = document.getElementById('searchJump');
  if (!jumpEl) return;
  while (jumpEl.firstChild) jumpEl.removeChild(jumpEl.firstChild);
  if (searchHits.length > 1) {
    const wrap = document.createElement('span');
    wrap.className = 'search-jump';
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '◀';
    prevBtn.title = '上一個';
    prevBtn.setAttribute('aria-label', '上一個匹配');
    prevBtn.addEventListener('click', function() { jumpHit(-1); });
    const counter = document.createElement('span');
    counter.className = 'hit-counter';
    counter.id = 'hitCounter';
    counter.textContent = '0/' + searchHits.length;
    const nextBtn = document.createElement('button');
    nextBtn.textContent = '▶';
    nextBtn.title = '下一個';
    nextBtn.setAttribute('aria-label', '下一個匹配');
    nextBtn.addEventListener('click', function() { jumpHit(1); });
    wrap.appendChild(prevBtn);
    wrap.appendChild(counter);
    wrap.appendChild(nextBtn);
    jumpEl.appendChild(wrap);
  }
}

function jumpHit(dir) {
  if (!searchHits.length) return;
  if (currentHitIdx >= 0 && currentHitIdx < searchHits.length) searchHits[currentHitIdx].classList.remove('current');
  currentHitIdx += dir;
  if (currentHitIdx >= searchHits.length) currentHitIdx = 0;
  if (currentHitIdx < 0) currentHitIdx = searchHits.length - 1;
  var target = searchHits[currentHitIdx];
  /* 確保 content-visibility 不影響捲動計算 */
  var card = target.closest('.subject-card');
  if (card) card.style.contentVisibility = 'visible';
  target.classList.add('current');
  requestAnimationFrame(function() { scrollToWithOffset(target); });
  const counter = document.getElementById('hitCounter');
  if (counter) counter.textContent = (currentHitIdx + 1) + '/' + searchHits.length;
}

/* === Hamburger === */
document.addEventListener('DOMContentLoaded', function() {
  const hamburger = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('sidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  function closeMobileSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('active');
    if (hamburger) { hamburger.textContent = '☰'; hamburger.setAttribute('aria-expanded', 'false'); }
  }
  if (hamburger) {
    hamburger.addEventListener('click', function() {
      const open = sidebar.classList.toggle('open');
      sidebarOverlay.classList.toggle('active');
      hamburger.textContent = open ? '✕' : '☰';
      hamburger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    sidebarOverlay.addEventListener('click', closeMobileSidebar);
    sidebar.querySelectorAll('.sidebar-link').forEach(function(l) {
      l.addEventListener('click', function() { if (window.innerWidth <= 768) closeMobileSidebar(); });
    });
    /* 滑動關閉 sidebar */
    var touchStartX = 0, touchStartY = 0, swiping = false;
    sidebar.addEventListener('touchstart', function(e) {
      if (e.touches.length > 1) return;
      touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; swiping = true;
    }, { passive: true });
    sidebar.addEventListener('touchmove', function(e) {
      if (!swiping) return;
      var dy = Math.abs(e.touches[0].clientY - touchStartY);
      if (dy > 30) swiping = false; /* 垂直滾動取消水平判定 */
    }, { passive: true });
    sidebar.addEventListener('touchend', function(e) {
      if (!swiping) return; swiping = false;
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (dx < -60 && sidebar.classList.contains('open')) closeMobileSidebar();
    }, { passive: true });
    sidebar.addEventListener('touchcancel', function() { swiping = false; }, { passive: true });
  }

  /* Sidebar toggle */
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarReopen = document.getElementById('sidebarReopen');
  try { if (localStorage.getItem('sidebar-collapsed') === '1') document.body.classList.add('sidebar-collapsed'); } catch(e) {}
  if (sidebarToggle) sidebarToggle.addEventListener('click', function() { document.body.classList.add('sidebar-collapsed'); try { localStorage.setItem('sidebar-collapsed', '1'); } catch(e) {} });
  if (sidebarReopen) sidebarReopen.addEventListener('click', function() { document.body.classList.remove('sidebar-collapsed'); try { localStorage.setItem('sidebar-collapsed', '0'); } catch(e) {} });

  /* Back to top (throttled scroll) */
  const backToTop = document.getElementById('backToTop');
  var scrollTicking = false;
  window.addEventListener('scroll', function() {
    if (!scrollTicking) { scrollTicking = true; requestAnimationFrame(function() { backToTop.classList.toggle('visible', window.scrollY > 400); scrollTicking = false; }); }
  }, { passive: true });
  backToTop.addEventListener('click', function() { window.scrollTo({ top: 0, behavior: 'smooth' }); });

  /* Sidebar accordion */
  document.querySelectorAll('.sidebar-year').forEach(function(y) {
    y.addEventListener('click', function() {
      toggleYear(y);
      document.querySelectorAll('.sidebar-year.active').forEach(function(ay) { if (ay !== y) { ay.classList.remove('active'); ay.setAttribute('aria-expanded', 'false'); } });
    });
    y.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); y.click(); } });
  });

  /* ARIA + keyboard for subject headers */
  document.querySelectorAll('.subject-card').forEach(function(card) {
    const header = card.querySelector('.subject-header');
    if (header) {
      header.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); } });
    }
  });

  /* Keyboard shortcuts */
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && !e.target.closest('input,textarea'))) {
      e.preventDefault(); document.getElementById('searchInput').focus();
    }
    if (e.key === 'Escape') {
      /* 搜尋框 Escape */
      if (document.activeElement === document.getElementById('searchInput')) {
        document.getElementById('searchInput').value = ''; doSearch(''); document.getElementById('searchInput').blur();
        return;
      }
      /* 匯出面板 Escape */
      var exportPanel = document.getElementById('exportPanel');
      if (exportPanel && exportPanel.style.display !== 'none') {
        hideExportPanel();
        return;
      }
      /* 手機 sidebar Escape */
      if (sidebar.classList.contains('open')) {
        closeMobileSidebar();
        return;
      }
    }
  });

  /* Populate subject filter */
  if (typeof SUBJECT_KEYS !== 'undefined') {
    const sel = document.getElementById('subjectFilter');
    SUBJECT_KEYS.forEach(function(sk) {
      const opt = document.createElement('option');
      opt.value = sk;
      opt.textContent = sk;
      sel.appendChild(opt);
    });
  }

  initBookmarks();
  initDarkMode();
  handleHash();
  window.addEventListener('hashchange', handleHash);

  /* Pre-build search text cache */
  window._cardTextCache = new Map();
  document.querySelectorAll('#yearView .subject-card').forEach(function(card) {
    window._cardTextCache.set(card, card.textContent.toLowerCase());
  });
});

/* === Bookmarks === */
function getStore(key) { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch(e) { return {}; } }
function setStore(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch(e) {} }

function initBookmarks() {
  const bookmarks = getStore('exam-bookmarks');
  document.querySelectorAll('#yearView .subject-card').forEach(function(card) {
    const id = card.id;
    if (!id) return;
    const header = card.querySelector('.subject-header');
    if (!header) return;
    const bmBtn = document.createElement('button');
    bmBtn.className = 'bookmark-btn' + (bookmarks[id] ? ' active' : '');
    bmBtn.textContent = bookmarks[id] ? '★' : '☆';
    bmBtn.title = '書籤';
    bmBtn.setAttribute('aria-label', '切換書籤');
    bmBtn.setAttribute('aria-pressed', bookmarks[id] ? 'true' : 'false');
    bmBtn.onclick = function(e) {
      e.stopPropagation();
      const bm = getStore('exam-bookmarks');
      if (bm[id]) { delete bm[id]; this.classList.remove('active'); this.textContent = '☆'; }
      else { bm[id] = true; this.classList.add('active'); this.textContent = '★'; }
      this.setAttribute('aria-pressed', bm[id] ? 'true' : 'false');
      setStore('exam-bookmarks', bm);
      const svCard = document.getElementById('sv-' + id);
      if (svCard) { const svBtn = svCard.querySelector('.bookmark-btn'); if (svBtn) { svBtn.classList.toggle('active', !!bm[id]); svBtn.textContent = bm[id] ? '★' : '☆'; } }
    };
    header.appendChild(bmBtn);
    header.removeAttribute('onclick');
    header.addEventListener('click', function(e) { if (e.target.closest('.bookmark-btn')) return; card.classList.toggle('open'); header.setAttribute('aria-expanded', card.classList.contains('open') ? 'true' : 'false'); });
  });
}

let bookmarkFilterActive = false;
function toggleBookmarkFilter() {
  bookmarkFilterActive = !bookmarkFilterActive;
  const btn = document.getElementById('bookmarkFilter');
  btn.classList.toggle('active', bookmarkFilterActive);
  btn.setAttribute('aria-pressed', bookmarkFilterActive ? 'true' : 'false');
  btn.textContent = bookmarkFilterActive ? '顯示全部' : '只看書籤';
  doSearch(document.getElementById('searchInput').value);
}

/* === Dark mode === */
function initDarkMode() {
  const toggle = document.getElementById('darkToggle');
  var saved = null; try { saved = localStorage.getItem('exam-dark'); } catch(e) {}
  if (saved === 'true' || (saved === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
  toggle.addEventListener('click', function() {
    const isDark = document.documentElement.classList.toggle('dark');
    try { localStorage.setItem('exam-dark', isDark); } catch(e) {}
  });
}

/* === 科目瀏覽 (Phase 5) === */
let subjectViewBuilt = false;
function switchView(mode) {
  currentView = mode;
  document.getElementById('yearView').style.display = mode === 'year' ? '' : 'none';
  document.getElementById('subjectView').style.display = mode === 'subject' ? '' : 'none';
  document.getElementById('viewYear').classList.toggle('active', mode === 'year');
  document.getElementById('viewSubject').classList.toggle('active', mode === 'subject');
  if (mode === 'subject' && !subjectViewBuilt) buildSubjectView();
  const q = document.getElementById('searchInput').value;
  if (q.trim() || activeYearFilter) doSearch(q);
  if (bookmarkFilterActive) { bookmarkFilterActive = false; toggleBookmarkFilter(); }
  if (practiceMode) {
    clearAllAnswerState();
    bindOptionClicks();
  }
}

function buildSubjectView() {
  const container = document.getElementById('subjectView');
  const groups = {};
  document.querySelectorAll('#yearView .year-section').forEach(function(ys) {
    const yearText = ys.querySelector('.year-heading').textContent.trim().replace('年', '');
    ys.querySelectorAll('.subject-card').forEach(function(card) {
      const subjectName = card.querySelector('.subject-header h3').textContent.trim();
      if (!groups[subjectName]) groups[subjectName] = [];
      groups[subjectName].push({ year: yearText, card: card });
    });
  });
  const sortedKeys = Object.keys(groups).sort();
  sortedKeys.forEach(function(key) {
    const section = document.createElement('div');
    section.className = 'subject-view-section';
    const heading = document.createElement('h2');
    heading.className = 'sv-heading';
    heading.textContent = key;
    section.appendChild(heading);
    groups[key].forEach(function(item) {
      const clone = item.card.cloneNode(true);
      clone.classList.remove('open');
      const origId = clone.id;
      if (origId) clone.id = 'sv-' + origId;
      clone.setAttribute('data-card-id', origId);
      const header = clone.querySelector('.subject-header h3');
      if (header) {
        const tag = document.createElement('span');
        tag.className = 'sv-year-tag';
        tag.textContent = item.year + '年';
        header.appendChild(tag);
      }
      const hdr = clone.querySelector('.subject-header');
      if (hdr) {
        hdr.removeAttribute('onclick');
        (function(c, h) {
          h.addEventListener('click', function(e) { if (!e.target.closest('.bookmark-btn')) { c.classList.toggle('open'); h.setAttribute('aria-expanded', c.classList.contains('open') ? 'true' : 'false'); } });
        })(clone, hdr);
      }
      const bmBtn = clone.querySelector('.bookmark-btn');
      if (bmBtn) {
        (function(btn, cid) {
          btn.onclick = function(e) {
            e.stopPropagation();
            const bm = getStore('exam-bookmarks');
            if (bm[cid]) { delete bm[cid]; btn.classList.remove('active'); btn.textContent = '☆'; }
            else { bm[cid] = true; btn.classList.add('active'); btn.textContent = '★'; }
            setStore('exam-bookmarks', bm);
            const origCard = document.getElementById(cid);
            if (origCard) {
              const ob = origCard.querySelector('.bookmark-btn');
              if (ob) { ob.classList.toggle('active', !!bm[cid]); ob.textContent = bm[cid] ? '★' : '☆'; }
            }
          };
        })(bmBtn, origId);
      }
      section.appendChild(clone);
    });
    container.appendChild(section);
  });
  subjectViewBuilt = true;
  if (window._cardTextCache) {
    document.querySelectorAll('#subjectView .subject-card').forEach(function(card) {
      window._cardTextCache.set(card, card.textContent.toLowerCase());
    });
  }
}

function filterBySubject(key) {
  const vs = getActiveViewSelector();
  if (!key) {
    document.querySelectorAll(vs + ' .subject-card').forEach(function(c) { c.style.display = ''; });
    document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) { s.style.display = ''; });
    return;
  }
  document.querySelectorAll(vs + ' .subject-card').forEach(function(card) {
    const name = card.querySelector('.subject-header h3').textContent.trim();
    card.style.display = name.indexOf(key) !== -1 ? '' : 'none';
  });
  document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) {
    s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
  });
}

/* === 練習模式 (Phase 6) — 互動式點選 === */
let practiceMode = false;
let practiceCorrect = 0;
let practiceTotal = 0;

function togglePractice() {
  practiceMode = !practiceMode;
  const btn = document.getElementById('practiceToggle');
  const scorePanel = document.getElementById('practiceScore');
  if (practiceMode) {
    document.body.classList.add('practice-mode');
    btn.classList.add('practice-active');
    btn.textContent = '結束練習';
    scorePanel.classList.add('visible');
    var session = getStore('exam-practice-session');
    if (session.url === window.location.pathname && session.ts && Date.now() - session.ts < 3600000) {
      practiceCorrect = session.correct || 0;
      practiceTotal = session.total || 0;
    } else {
      practiceCorrect = 0;
      practiceTotal = 0;
    }
    updateScoreUI();
    bindOptionClicks();
  } else {
    if (practiceTotal > 0) savePracticeScore(practiceCorrect, practiceTotal);
    clearPracticeSession();
    document.body.classList.remove('practice-mode');
    btn.classList.remove('practice-active');
    btn.textContent = '練習模式';
    scorePanel.classList.remove('visible');
    clearAllAnswerState();
  }
}

function bindOptionClicks() {
  document.querySelectorAll('.mc-opt').forEach(function(opt) {
    if (opt._boundClick) return;
    opt._boundClick = true;
    opt.addEventListener('click', function() {
      if (!practiceMode) return;
      var block = opt.closest('.q-block');
      if (!block || block.classList.contains('answered')) return;
      var answer = block.getAttribute('data-answer');
      var chosen = opt.getAttribute('data-val');
      block.classList.add('answered');
      practiceTotal++;
      if (chosen === answer) {
        practiceCorrect++;
        opt.classList.add('correct');
      } else {
        opt.classList.add('wrong');
        block.querySelectorAll('.mc-opt').forEach(function(o) {
          if (o.getAttribute('data-val') === answer) o.classList.add('correct-reveal');
        });
      }
      var ansEl = block.querySelector('.q-answer');
      if (ansEl) ansEl.classList.add('revealed');
      updateScoreUI();
      savePracticeSession();
    });
  });
}

function updateScoreUI() {
  document.getElementById('scoreCorrect').textContent = practiceCorrect;
  document.getElementById('scoreTotal').textContent = practiceTotal;
  var pct = practiceTotal > 0 ? Math.round(practiceCorrect / practiceTotal * 100) : 0;
  document.getElementById('scorePct').textContent = practiceTotal > 0 ? pct + '%' : '--';
}

function clearAllAnswerState() {
  document.querySelectorAll('.q-block').forEach(function(b) {
    b.classList.remove('answered');
  });
  document.querySelectorAll('.mc-opt').forEach(function(o) {
    o.classList.remove('correct', 'wrong', 'correct-reveal', 'selected');
  });
  document.querySelectorAll('.q-answer').forEach(function(a) {
    a.classList.remove('revealed');
  });
}

function resetScore() {
  practiceCorrect = 0;
  practiceTotal = 0;
  updateScoreUI();
  clearPracticeSession();
  clearAllAnswerState();
}

/* === 一般模式：顯示/隱藏全部答案 === */
function toggleAllAnswers(btn) {
  var showing = btn.classList.toggle('active');
  btn.textContent = showing ? '隱藏答案' : '顯示答案';
  document.querySelectorAll('.q-block').forEach(function(b) {
    if (showing) b.classList.add('show-answer');
    else b.classList.remove('show-answer');
  });
}

/* === URL Hash 導航 (Phase 7) === */
function scrollToWithOffset(el) {
  const y = el.getBoundingClientRect().top + window.scrollY - 140;
  window.scrollTo({ top: y, behavior: 'smooth' });
}

function handleHash() {
  const hash = window.location.hash.replace('#', '');
  if (!hash) return;
  if (currentView === 'subject') switchView('year');
  const yearMatch = hash.match(/^year-(\d+)$/);
  if (yearMatch) {
    const yearEl = document.getElementById('year-' + yearMatch[1]);
    if (yearEl) {
      document.querySelectorAll('.sidebar-year').forEach(function(sy) {
        if (sy.textContent.trim().startsWith(yearMatch[1])) sy.classList.add('active');
      });
      requestAnimationFrame(function() { requestAnimationFrame(function() { scrollToWithOffset(yearEl); }); });
    }
    return;
  }
  const cardEl = document.getElementById(hash);
  if (cardEl && cardEl.classList.contains('subject-card')) {
    cardEl.classList.add('open');
    const hdr = cardEl.querySelector('.subject-header');
    if (hdr) hdr.setAttribute('aria-expanded', 'true');
    const yearSection = cardEl.closest('.year-section');
    if (yearSection) {
      const yNum = yearSection.id.replace('year-', '');
      document.querySelectorAll('.sidebar-year').forEach(function(sy) {
        if (sy.textContent.trim().startsWith(yNum)) sy.classList.add('active');
      });
    }
    requestAnimationFrame(function() { requestAnimationFrame(function() { scrollToWithOffset(cardEl); }); });
  }
}

/* === 練習歷史 (Phase 8) === */
function savePracticeScore(correct, total) {
  const history = getStore('exam-practice-history');
  if (!history.scores) history.scores = [];
  history.scores.unshift({
    correct: correct,
    total: total,
    pct: Math.round(correct / total * 100),
    date: new Date().toISOString()
  });
  if (history.scores.length > 20) history.scores = history.scores.slice(0, 20);
  setStore('exam-practice-history', history);
}

/* === 練習 Session 持久化 === */
function savePracticeSession() {
  if (!practiceMode) return;
  setStore('exam-practice-session', {
    correct: practiceCorrect,
    total: practiceTotal,
    url: window.location.pathname,
    ts: Date.now()
  });
}
function clearPracticeSession() {
  try { localStorage.removeItem('exam-practice-session'); } catch(e) {}
}

/* === 匯出 PDF (Phase 9) === */
function showExportPanel() {
  var panel = document.getElementById('exportPanel');
  var isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : '';
  /* 手機底部彈出板需要 overlay */
  if (window.innerWidth <= 768) {
    var overlay = document.getElementById('sidebarOverlay');
    if (!isOpen) { overlay.classList.add('active'); overlay.onclick = function() { hideExportPanel(); }; }
    else { overlay.classList.remove('active'); overlay.onclick = function() { var sidebar = document.getElementById('sidebar'); sidebar.classList.remove('open'); overlay.classList.remove('active'); if (document.getElementById('hamburgerBtn')) { document.getElementById('hamburgerBtn').textContent = '☰'; document.getElementById('hamburgerBtn').setAttribute('aria-expanded', 'false'); } }; }
  }
}
function hideExportPanel() {
  document.getElementById('exportPanel').style.display = 'none';
  if (window.innerWidth <= 768) { var overlay = document.getElementById('sidebarOverlay'); overlay.classList.remove('active'); }
}
function exportPDF(includeAnswers) {
  hideExportPanel();
  var vs = getActiveViewSelector();
  var cards = document.querySelectorAll(vs + ' .subject-card');
  var otherView = vs === '#yearView' ? '#subjectView' : '#yearView';

  document.querySelector(otherView).classList.add('print-hidden');

  var visibleCount = 0;
  cards.forEach(function(card) {
    if (card.style.display === 'none') {
      card.classList.add('print-hidden');
    } else {
      card.classList.add('open');
      visibleCount++;
    }
  });

  document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) {
    if (s.style.display === 'none') s.classList.add('print-hidden');
  });

  if (!includeAnswers) document.body.classList.add('print-no-answers');

  var header = document.createElement('div');
  header.className = 'print-header';
  header.id = 'printHeader';
  var h1 = document.createElement('h1');
  h1.textContent = document.querySelector('.page-title').textContent;
  var info = document.createElement('p');
  var filterInfo = [];
  if (activeYearFilter) filterInfo.push(activeYearFilter + '年');
  var searchVal = document.getElementById('searchInput').value.trim();
  if (searchVal) filterInfo.push('關鍵字: ' + searchVal);
  if (bookmarkFilterActive) filterInfo.push('僅書籤');
  var answerText = includeAnswers ? '含答案' : '不含答案';
  info.textContent = visibleCount + ' 份試卷 \u00b7 ' + answerText +
    (filterInfo.length ? ' \u00b7 篩選: ' + filterInfo.join(', ') : '') +
    ' \u00b7 ' + new Date().toLocaleDateString('zh-TW');
  header.appendChild(h1);
  header.appendChild(info);
  var mainEl = document.querySelector('.main');
  mainEl.insertBefore(header, mainEl.firstChild);

  window.print();

  var _cleaned = false;
  function cleanup() {
    if (_cleaned) return;
    _cleaned = true;
    var h = document.getElementById('printHeader');
    if (h) h.remove();
    document.body.classList.remove('print-no-answers');
    document.querySelectorAll('.print-hidden').forEach(function(el) { el.classList.remove('print-hidden'); });
  }
  if (window.onafterprint !== undefined) {
    window.addEventListener('afterprint', cleanup, { once: true });
  }
  setTimeout(cleanup, 30000);
}
