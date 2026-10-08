/* === search-engine.js — 跨類科全文搜尋引擎 === */
(function (window) {
  'use strict';

  var ms = null;
  var rawData = null;
  var loading = null;
  var FIELDS = ['cat','cats','yr','sub','no','type','passage','stem','optA','optB','optC','optD','ans'];

  function loadIndex(basePath) {
    if (loading) return loading;
    loading = fetch((basePath || '') + 'data/search-index.json')
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (!data.columns || !data.columns.passage || !data.columns.cats) {
          throw new Error('搜尋索引版本過舊，請重新部署');
        }
        rawData = data;
        buildIndex(data);
        return data.stats;
      })
      .catch(function (error) {
        loading = null;
        throw error;
      });
    return loading;
  }

  function buildIndex(data) {
    var columns = data.columns;
    var documents = new Array(columns.cat.length);
    for (var i = 0; i < documents.length; i++) {
      var document = { id: i };
      FIELDS.forEach(function (field) { document[field] = columns[field][i]; });
      documents[i] = document;
    }
    ms = new MiniSearch({
      fields: ['passage','stem','optA','optB','optC','optD','sub'],
      storeFields: ['cat','cats','yr','sub','no','type','ans'],
      searchOptions: {
        boost: { stem: 3, passage: 2, sub: 1 },
        prefix: true,
        fuzzy: 0.15,
        tokenize: function (text) {
          text = String(text || '');
          return text
            .replace(/[\s\-_,.;:!?()（）\[\]{}「」『』【】《》〈〉、。，；：！？\n\r]+/g, ' ')
            .split(/\s+/)
            .filter(Boolean)
            .concat(charTokens(text));
        }
      }
    });
    ms.addAll(documents);
  }

  function charTokens(text) {
    var chars = [];
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 0x4e00 && code <= 0x9fff) chars.push(text[i]);
    }
    return chars;
  }

  function belongs(categories, category) {
    if (!category) return true;
    return Array.isArray(categories) && categories.indexOf(category) !== -1;
  }

  function answerMatches(answer, filterAnswer) {
    if (!filterAnswer) return true;
    if (answer === '送分') return filterAnswer === '送分';
    return String(answer || '').split('或').indexOf(filterAnswer) !== -1;
  }

  function passes(result, filters) {
    if (!filters) return true;
    if (filters.yr && result.yr !== filters.yr) return false;
    if (filters.cat && !belongs(result.cats, filters.cat)) return false;
    if (filters.sub && result.sub !== filters.sub) return false;
    if (filters.type && result.type !== filters.type) return false;
    if (filters.ans && !answerMatches(result.ans, filters.ans)) return false;
    return true;
  }

  function search(query, filters, limit) {
    if (!ms || !rawData) return [];
    var max = limit || 100;
    var results;
    if (query && query.trim()) {
      results = ms.search(query.trim(), { limit: max, filter: function (result) { return passes(result, filters); } });
    } else {
      results = [];
      var columns = rawData.columns;
      for (var i = 0; i < columns.cat.length && results.length < max; i++) {
        var candidate = {
          id: i,
          cat: columns.cat[i], cats: columns.cats[i], yr: columns.yr[i], sub: columns.sub[i],
          type: columns.type[i], ans: columns.ans[i]
        };
        if (passes(candidate, filters)) results.push({ id: i, score: 0 });
      }
    }
    var columns = rawData.columns;
    return results.map(function (result) {
      var id = result.id;
      return {
        idx: id, score: result.score || 0,
        cat: columns.cat[id], cats: columns.cats[id], yr: columns.yr[id], sub: columns.sub[id],
        no: columns.no[id], type: columns.type[id], passage: columns.passage[id], stem: columns.stem[id],
        optA: columns.optA[id], optB: columns.optB[id], optC: columns.optC[id], optD: columns.optD[id],
        ans: columns.ans[id]
      };
    });
  }

  function getFacets() { return rawData ? rawData.facets : null; }
  function getStats() { return rawData ? rawData.stats : null; }

  window.SearchEngine = { loadIndex: loadIndex, search: search, getFacets: getFacets, getStats: getStats };
})(window);
