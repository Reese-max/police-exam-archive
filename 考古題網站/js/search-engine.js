/* 全站共用全文搜尋引擎：search-index schema v2。 */
(function (window) {
  'use strict';

  var ms = null;
  var rawData = null;
  var loading = null;

  var FIELDS = [
    'cat', 'cats', 'yr', 'sub', 'no', 'type', 'stem', 'passage',
    'optA', 'optB', 'optC', 'optD', 'ans'
  ];

  function loadIndex(basePath) {
    if (loading) return loading;
    loading = fetch((basePath || '') + 'data/search-index.json', { cache: 'no-cache' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        _validate(data);
        rawData = _upgradeLegacy(data);
        _buildIndex(rawData);
        return rawData.stats;
      })
      .catch(function (error) {
        loading = null;
        ms = null;
        rawData = null;
        throw error;
      });
    return loading;
  }

  function _validate(data) {
    if (!data || !data.columns || !Array.isArray(data.columns.cat)) {
      throw new Error('搜尋索引格式不正確');
    }
    var total = data.columns.cat.length;
    ['yr', 'sub', 'no', 'type', 'stem', 'optA', 'optB', 'optC', 'optD', 'ans']
      .forEach(function (field) {
        if (!Array.isArray(data.columns[field]) || data.columns[field].length !== total) {
          throw new Error('搜尋索引欄位不一致：' + field);
        }
      });
  }

  function _upgradeLegacy(data) {
    var columns = data.columns;
    var total = columns.cat.length;
    if (!Array.isArray(columns.cats)) {
      columns.cats = new Array(total);
      for (var i = 0; i < total; i++) columns.cats[i] = columns.cat[i] ? [columns.cat[i]] : [];
    }
    if (!Array.isArray(columns.passage)) {
      columns.passage = new Array(total).fill('');
    }
    data.v = data.v || 1;
    return data;
  }

  function _buildIndex(data) {
    var columns = data.columns;
    var total = columns.cat.length;
    var documents = new Array(total);

    for (var i = 0; i < total; i++) {
      var document = { id: i };
      for (var f = 0; f < FIELDS.length; f++) {
        document[FIELDS[f]] = columns[FIELDS[f]][i];
      }
      documents[i] = document;
    }

    ms = new MiniSearch({
      fields: ['stem', 'passage', 'optA', 'optB', 'optC', 'optD', 'sub'],
      storeFields: FIELDS,
      tokenize: _tokenize,
      searchOptions: {
        boost: { stem: 3, passage: 1.5, sub: 1 },
        prefix: true,
        fuzzy: 0.15
      }
    });
    ms.addAll(documents);
  }

  function _tokenize(text) {
    text = String(text || '');
    return text
      .replace(/[\s\-_,.;:!?()（）\[\]{}「」『』【】《》〈〉、。，；：！？\n\r]+/g, ' ')
      .split(/\s+/)
      .filter(Boolean)
      .concat(_charTokens(text));
  }

  function _charTokens(text) {
    var chars = [];
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 0x4e00 && code <= 0x9fff) chars.push(text[i]);
    }
    return chars;
  }

  function _categories(value, fallback) {
    if (Array.isArray(value)) return value;
    if (typeof value === 'string' && value) {
      try {
        var parsed = JSON.parse(value);
        if (Array.isArray(parsed)) return parsed;
      } catch (error) {}
      return value.split('|').filter(Boolean);
    }
    return fallback ? [fallback] : [];
  }

  function _answerMatches(answer, filter) {
    if (!filter) return true;
    answer = String(answer || '').normalize('NFKC').toUpperCase().replace(/\s+/g, '');
    filter = String(filter).normalize('NFKC').toUpperCase().replace(/\s+/g, '');
    if (filter === '送分') return answer.indexOf('送分') !== -1 || answer === '*';
    return answer.match(/[A-D]/g) ? answer.match(/[A-D]/g).indexOf(filter) !== -1 : false;
  }

  function _passes(item, filters) {
    if (!filters) return true;
    if (filters.yr && item.yr !== filters.yr) return false;
    if (filters.cat && _categories(item.cats, item.cat).indexOf(filters.cat) === -1) return false;
    if (filters.sub && item.sub !== filters.sub) return false;
    if (filters.type && item.type !== filters.type) return false;
    if (filters.ans && !_answerMatches(item.ans, filters.ans)) return false;
    return true;
  }

  function _row(index, score) {
    var columns = rawData.columns;
    return {
      idx: index,
      score: score || 0,
      cat: columns.cat[index],
      cats: _categories(columns.cats[index], columns.cat[index]),
      yr: columns.yr[index],
      sub: columns.sub[index],
      no: columns.no[index],
      type: columns.type[index],
      stem: columns.stem[index],
      passage: columns.passage[index] || '',
      optA: columns.optA[index],
      optB: columns.optB[index],
      optC: columns.optC[index],
      optD: columns.optD[index],
      ans: columns.ans[index]
    };
  }

  function search(query, filters, limit) {
    if (!ms || !rawData) return [];
    var max = Number.isFinite(limit) && limit > 0 ? limit : 100;
    var results = [];

    if (query && String(query).trim()) {
      var found = ms.search(String(query).trim(), { limit: max * 4 });
      for (var i = 0; i < found.length && results.length < max; i++) {
        var item = _row(found[i].id, found[i].score);
        if (_passes(item, filters)) results.push(item);
      }
      return results;
    }

    for (var index = 0; index < rawData.columns.cat.length && results.length < max; index++) {
      var row = _row(index, 0);
      if (_passes(row, filters)) results.push(row);
    }
    return results;
  }

  function getFacets() {
    return rawData ? rawData.facets : null;
  }

  function getStats() {
    return rawData ? rawData.stats : null;
  }

  function getVersion() {
    return rawData ? rawData.v : null;
  }

  window.SearchEngine = {
    loadIndex: loadIndex,
    search: search,
    getFacets: getFacets,
    getStats: getStats,
    getVersion: getVersion
  };
})(window);
