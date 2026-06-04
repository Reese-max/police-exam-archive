/* === search-engine.js — 跨部門全文搜尋引擎 === */
/* 依賴：MiniSearch (CDN) + search-index.json */
(function (window) {
  'use strict';

  var ms = null;        // MiniSearch 實例
  var rawData = null;   // 原始 column-oriented 資料
  var loading = null;   // Promise cache

  /* 欄位定義（與 build_search_index.py 同步） */
  var FIELDS = ['cat', 'yr', 'sub', 'no', 'type', 'stem', 'optA', 'optB', 'optC', 'optD', 'ans'];

  /* ── 載入索引 ── */
  function loadIndex(basePath) {
    if (loading) return loading;
    loading = fetch((basePath || '') + 'data/search-index.json')
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        rawData = data;
        _buildIndex(data);
        return data.stats;
      })
      .catch(function (err) {
        loading = null; // 失敗時清除快取，讓頁面可重試（避免 rejected Promise 永久毒化）
        throw err;
      });
    return loading;
  }

  /* ── 建立 MiniSearch 索引 ── */
  function _buildIndex(data) {
    var cols = data.columns;
    var total = cols.cat.length;

    // 將 column-oriented 轉為 documents 陣列（MiniSearch 需要）
    var docs = new Array(total);
    for (var i = 0; i < total; i++) {
      var doc = { id: i };
      for (var f = 0; f < FIELDS.length; f++) {
        doc[FIELDS[f]] = cols[FIELDS[f]][i];
      }
      docs[i] = doc;
    }

    ms = new MiniSearch({
      fields: ['stem', 'optA', 'optB', 'optC', 'optD', 'sub'],
      storeFields: ['cat', 'yr', 'sub', 'no', 'type', 'ans'],
      searchOptions: {
        boost: { stem: 3, sub: 1 },
        prefix: true,
        fuzzy: 0.15,
        tokenize: function (text) {
          // 中文：逐字 + 保留完整詞（用空格/標點分割）
          return text
            .replace(/[\s\-_,.;:!?()（）\[\]{}「」『』【】《》〈〉、。，；：！？\n\r]+/g, ' ')
            .split(/\s+/)
            .filter(Boolean)
            .concat(_charTokens(text));
        }
      }
    });
    ms.addAll(docs);
  }

  /* 中文字元級 token（讓「基本權」能匹配「基本權利」） */
  function _charTokens(text) {
    var chars = [];
    for (var i = 0; i < text.length; i++) {
      var c = text[i];
      if (c.charCodeAt(0) >= 0x4e00 && c.charCodeAt(0) <= 0x9fff) {
        chars.push(c);
      }
    }
    return chars;
  }

  /* ── 搜尋 ── */
  /**
   * @param {string} query - 搜尋關鍵字
   * @param {Object} filters - { yr, cat, sub, type, ans }
   * @param {number} limit - 上限
   * @returns {Array} 結果陣列
   */
  function search(query, filters, limit) {
    if (!ms || !rawData) return [];

    var opts = {
      limit: limit || 100,
      filter: function (result) {
        if (filters) {
          if (filters.yr && result.yr !== filters.yr) return false;
          if (filters.cat && result.cat !== filters.cat) return false;
          if (filters.sub && result.sub !== filters.sub) return false;
          if (filters.type && result.type !== filters.type) return false;
          if (filters.ans && result.ans !== filters.ans) return false;
        }
        return true;
      }
    };

    var results;
    if (query && query.trim()) {
      results = ms.search(query.trim(), opts);
    } else {
      // 無關鍵字 → 純篩選
      var cols = rawData.columns;
      results = [];
      for (var i = 0; i < cols.cat.length && results.length < (limit || 100); i++) {
        var pass = true;
        if (filters) {
          if (filters.yr && cols.yr[i] !== filters.yr) pass = false;
          if (filters.cat && cols.cat[i] !== filters.cat) pass = false;
          if (filters.sub && cols.sub[i] !== filters.sub) pass = false;
          if (filters.type && cols.type[i] !== filters.type) pass = false;
          if (filters.ans && cols.ans[i] !== filters.ans) pass = false;
        }
        if (pass) results.push({ id: i, score: 0 });
      }
    }

    // 附加完整資料
    var cols = rawData.columns;
    return results.map(function (r) {
      return {
        idx: r.id,
        score: r.score || 0,
        cat: cols.cat[r.id],
        yr: cols.yr[r.id],
        sub: cols.sub[r.id],
        no: cols.no[r.id],
        type: cols.type[r.id],
        stem: cols.stem[r.id],
        optA: cols.optA[r.id],
        optB: cols.optB[r.id],
        optC: cols.optC[r.id],
        optD: cols.optD[r.id],
        ans: cols.ans[r.id],
      };
    });
  }

  /* ── facets（篩選選項）── */
  function getFacets() {
    if (!rawData) return null;
    return rawData.facets;
  }

  function getStats() {
    if (!rawData) return null;
    return rawData.stats;
  }

  /* ── 匯出 ── */
  window.SearchEngine = {
    loadIndex: loadIndex,
    search: search,
    getFacets: getFacets,
    getStats: getStats,
  };
})(window);
