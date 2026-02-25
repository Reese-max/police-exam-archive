/* === pdf-export.js — 手機端 PDF 匯出引擎 === */
/* 依賴：pdf-lib (window.PDFLib), @pdf-lib/fontkit (window.fontkit) */
/* 由 app.js 動態載入，僅在行動裝置上使用 */

(function (window) {
  'use strict';

  /* ── 常數 ── */
  var PAGE_W = 595.28;  // A4 pt
  var PAGE_H = 841.89;
  var MARGIN = { top: 50, right: 50, bottom: 45, left: 55 };
  var CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;
  var CONTENT_H = PAGE_H - MARGIN.top - MARGIN.bottom;

  var FONT_SIZE = {
    title: 16,
    yearHeading: 14,
    subjectHeading: 12,
    body: 10,
    small: 8.5,
    footer: 8
  };

  var LINE_HEIGHT_FACTOR = 1.6;
  var PARAGRAPH_GAP = 6;

  /* ── 2a. 資料擷取層 ── */

  /**
   * 從 DOM 擷取匯出資料
   * @param {{years: string[], subjects: string[]}} selection
   * @param {boolean} includeAnswers
   * @returns {Array<{year: string, subjects: Array}>}
   */
  function extractExamData(selection, includeAnswers) {
    var result = [];
    var sections = document.querySelectorAll('#yearView .year-section');

    sections.forEach(function (sec) {
      var headingEl = sec.querySelector('.year-heading');
      if (!headingEl) return;
      var headingText = headingEl.textContent.trim();
      var yearMatch = headingText.match(/(\d+)/);
      if (!yearMatch || selection.years.indexOf(yearMatch[1]) === -1) return;

      var yearData = { year: yearMatch[1] + '年', subjects: [] };

      sec.querySelectorAll('.subject-card').forEach(function (card) {
        var nameEl = card.querySelector('.subject-header h3');
        if (!nameEl) return;
        var subjectName = nameEl.textContent.trim();
        // 移除 sv-year-tag 的文字
        var yearTag = nameEl.querySelector('.sv-year-tag');
        if (yearTag) subjectName = subjectName.replace(yearTag.textContent, '').trim();

        if (selection.subjects.indexOf(subjectName) === -1) return;

        var subjectData = { name: subjectName, metaTags: [], contentItems: [] };

        // meta tags
        card.querySelectorAll('.meta-tag').forEach(function (tag) {
          subjectData.metaTags.push(tag.textContent.trim());
        });

        // 內容項目
        var body = card.querySelector('.subject-body');
        if (!body) return;

        var contentEl = body.querySelector('.exam-content-v2') || body;
        var children = contentEl.children;

        for (var i = 0; i < children.length; i++) {
          var el = children[i];
          var cls = el.className || '';

          if (cls.indexOf('exam-note') !== -1) {
            subjectData.contentItems.push({
              type: 'note',
              text: el.textContent.trim()
            });
          } else if (cls.indexOf('exam-section-marker') !== -1) {
            subjectData.contentItems.push({
              type: 'section-marker',
              text: el.textContent.trim()
            });
          } else if (cls.indexOf('essay-question') !== -1) {
            subjectData.contentItems.push({
              type: 'essay',
              text: el.textContent.trim()
            });
          } else if (cls.indexOf('q-block') !== -1) {
            var qItem = _extractQBlock(el, includeAnswers);
            if (qItem) subjectData.contentItems.push(qItem);
          } else if (cls.indexOf('figure-block') !== -1) {
            var img = el.querySelector('img');
            if (img) {
              subjectData.contentItems.push({
                type: 'figure',
                src: img.src,
                alt: img.alt || ''
              });
            }
          } else if (cls.indexOf('reading-passage') !== -1) {
            subjectData.contentItems.push({
              type: 'passage',
              text: el.textContent.trim()
            });
          }
        }

        yearData.subjects.push(subjectData);
      });

      if (yearData.subjects.length > 0) result.push(yearData);
    });

    return result;
  }

  function _extractQBlock(block, includeAnswers) {
    var qEl = block.querySelector('.mc-question');
    if (!qEl) return null;

    var numEl = qEl.querySelector('.q-number');
    var textEl = qEl.querySelector('.q-text');
    var qNum = numEl ? numEl.textContent.trim() : '';
    var qText = textEl ? textEl.textContent.trim() : '';

    var options = [];
    block.querySelectorAll('.mc-opt').forEach(function (opt) {
      var label = opt.querySelector('.opt-label');
      var text = opt.querySelector('.opt-text');
      options.push({
        label: label ? label.textContent.trim() : '',
        text: text ? text.textContent.trim() : ''
      });
    });

    var answer = '';
    if (includeAnswers) {
      var ansEl = block.querySelector('.q-answer');
      if (ansEl) answer = ansEl.textContent.trim();
    }

    // 題目內的圖片
    var figures = [];
    block.querySelectorAll('.figure-block img').forEach(function (img) {
      figures.push({ src: img.src, alt: img.alt || '' });
    });

    return {
      type: 'mc-question',
      num: qNum,
      text: qText,
      options: options,
      answer: answer,
      figures: figures
    };
  }

  /* ── 2b. CJK 文字換行引擎 ── */

  var _widthCache = new Map();

  function _isCJK(code) {
    return (code >= 0x4E00 && code <= 0x9FFF) ||
           (code >= 0x3000 && code <= 0x303F) ||
           (code >= 0xFF00 && code <= 0xFFEF) ||
           (code >= 0x3400 && code <= 0x4DBF) ||
           (code >= 0xF900 && code <= 0xFAFF);
  }

  function _charWidth(ch, fontSize, font) {
    var key = ch + '|' + fontSize;
    if (_widthCache.has(key)) return _widthCache.get(key);

    var w;
    try {
      w = font.widthOfTextAtSize(ch, fontSize);
    } catch (e) {
      // 字元不在字型中，用空格寬度代替
      w = font.widthOfTextAtSize(' ', fontSize);
    }
    _widthCache.set(key, w);
    return w;
  }

  /**
   * 將文字斷行
   * @param {string} text
   * @param {number} fontSize
   * @param {PDFFont} font
   * @param {number} maxWidth
   * @returns {string[]}
   */
  function breakTextIntoLines(text, fontSize, font, maxWidth) {
    if (!text) return [''];
    var lines = [];
    var paragraphs = text.split('\n');

    for (var p = 0; p < paragraphs.length; p++) {
      var para = paragraphs[p];
      if (!para.trim()) {
        lines.push('');
        continue;
      }
      var currentLine = '';
      var currentWidth = 0;
      var i = 0;

      while (i < para.length) {
        var ch = para[i];
        var code = para.charCodeAt(i);
        var w = _charWidth(ch, fontSize, font);

        if (currentWidth + w > maxWidth && currentLine.length > 0) {
          // 需要換行
          if (_isCJK(code)) {
            // CJK 字元任意處可斷
            lines.push(currentLine);
            currentLine = ch;
            currentWidth = w;
          } else if (ch === ' ') {
            // 空格處斷行
            lines.push(currentLine);
            currentLine = '';
            currentWidth = 0;
          } else {
            // 拉丁文：回溯到最近空格
            var spaceIdx = currentLine.lastIndexOf(' ');
            if (spaceIdx > 0) {
              lines.push(currentLine.substring(0, spaceIdx));
              currentLine = currentLine.substring(spaceIdx + 1) + ch;
              // 重新計算寬度
              currentWidth = 0;
              for (var j = 0; j < currentLine.length; j++) {
                currentWidth += _charWidth(currentLine[j], fontSize, font);
              }
            } else {
              // 沒有空格可回溯，強制斷行
              lines.push(currentLine);
              currentLine = ch;
              currentWidth = w;
            }
          }
        } else {
          currentLine += ch;
          currentWidth += w;
        }
        i++;
      }
      if (currentLine) lines.push(currentLine);
    }

    return lines.length ? lines : [''];
  }

  /* ── 2c. PDF 版面引擎 ── */

  function PdfLayoutEngine(pdfDoc, font, onProgress) {
    this.doc = pdfDoc;
    this.font = font;
    this.onProgress = onProgress || function () {};
    this.pages = [];
    this.currentPage = null;
    this.cursorY = 0;
    this.pageNum = 0;
    this.headerTitle = '';
    this.headerDate = '';
  }

  PdfLayoutEngine.prototype._newPage = function () {
    this.pageNum++;
    var page = this.doc.addPage([PAGE_W, PAGE_H]);
    this.pages.push(page);
    this.currentPage = page;
    this.cursorY = PAGE_H - MARGIN.top;

    // 頁首（非第一頁）
    if (this.pageNum > 1 && this.headerTitle) {
      page.drawText(this.headerTitle, {
        x: MARGIN.left,
        y: PAGE_H - 25,
        size: FONT_SIZE.small,
        font: this.font,
        color: _rgb(0.4, 0.4, 0.4)
      });
      page.drawText(this.headerDate, {
        x: PAGE_W - MARGIN.right - this.font.widthOfTextAtSize(this.headerDate, FONT_SIZE.small),
        y: PAGE_H - 25,
        size: FONT_SIZE.small,
        font: this.font,
        color: _rgb(0.4, 0.4, 0.4)
      });
      // 頁首分隔線
      page.drawLine({
        start: { x: MARGIN.left, y: PAGE_H - 30 },
        end: { x: PAGE_W - MARGIN.right, y: PAGE_H - 30 },
        thickness: 0.5,
        color: _rgb(0.8, 0.8, 0.8)
      });
      this.cursorY = PAGE_H - MARGIN.top - 5;
    }

    return page;
  };

  PdfLayoutEngine.prototype._ensureSpace = function (needed) {
    if (this.cursorY - needed < MARGIN.bottom) {
      this._drawPageFooter();
      this._newPage();
    }
  };

  PdfLayoutEngine.prototype._drawPageFooter = function () {
    if (!this.currentPage) return;
    var text = '- ' + this.pageNum + ' -';
    var w = this.font.widthOfTextAtSize(text, FONT_SIZE.footer);
    this.currentPage.drawText(text, {
      x: (PAGE_W - w) / 2,
      y: 20,
      size: FONT_SIZE.footer,
      font: this.font,
      color: _rgb(0.5, 0.5, 0.5)
    });
  };

  PdfLayoutEngine.prototype._drawText = function (text, fontSize, options) {
    var opts = options || {};
    var x = opts.x || MARGIN.left;
    var color = opts.color || _rgb(0, 0, 0);
    var indent = opts.indent || 0;
    var maxW = opts.maxWidth || (CONTENT_W - indent);

    var lines = breakTextIntoLines(text, fontSize, this.font, maxW);
    var lineH = fontSize * LINE_HEIGHT_FACTOR;

    for (var i = 0; i < lines.length; i++) {
      this._ensureSpace(lineH);
      this.cursorY -= lineH;

      if (lines[i]) {
        // 過濾掉字型不支援的字元
        var safeText = _sanitizeText(lines[i]);
        try {
          this.currentPage.drawText(safeText, {
            x: x + indent,
            y: this.cursorY,
            size: fontSize,
            font: this.font,
            color: color
          });
        } catch (e) {
          // 字元編碼錯誤，逐字繪製
          this._drawTextCharByChar(safeText, x + indent, this.cursorY, fontSize, color);
        }
      }
    }
    return lines.length * lineH;
  };

  PdfLayoutEngine.prototype._drawTextCharByChar = function (text, x, y, fontSize, color) {
    var cx = x;
    for (var i = 0; i < text.length; i++) {
      try {
        this.currentPage.drawText(text[i], {
          x: cx, y: y, size: fontSize, font: this.font, color: color
        });
        cx += _charWidth(text[i], fontSize, this.font);
      } catch (e) {
        // 跳過無法繪製的字元
        cx += _charWidth(' ', fontSize, this.font);
      }
    }
  };

  /* 繪製年度標題 */
  PdfLayoutEngine.prototype.drawYearHeading = function (text) {
    var lineH = FONT_SIZE.yearHeading * LINE_HEIGHT_FACTOR;
    this._ensureSpace(lineH + 10);

    // 分隔線
    this.cursorY -= 8;
    this.currentPage.drawLine({
      start: { x: MARGIN.left, y: this.cursorY },
      end: { x: PAGE_W - MARGIN.right, y: this.cursorY },
      thickness: 1.5,
      color: _rgb(0.15, 0.39, 0.92) // #2563eb
    });

    this.cursorY -= lineH + 2;
    var safeText = _sanitizeText(text);
    try {
      this.currentPage.drawText(safeText, {
        x: MARGIN.left,
        y: this.cursorY,
        size: FONT_SIZE.yearHeading,
        font: this.font,
        color: _rgb(0.15, 0.39, 0.92)
      });
    } catch (e) {
      this._drawTextCharByChar(safeText, MARGIN.left, this.cursorY, FONT_SIZE.yearHeading, _rgb(0.15, 0.39, 0.92));
    }
    this.cursorY -= 6;
  };

  /* 繪製科目標題 */
  PdfLayoutEngine.prototype.drawSubjectHeading = function (text, metaTags) {
    var lineH = FONT_SIZE.subjectHeading * LINE_HEIGHT_FACTOR;
    this._ensureSpace(lineH + 20);

    this.cursorY -= 10;

    // 背景矩形
    this.currentPage.drawRectangle({
      x: MARGIN.left,
      y: this.cursorY - lineH - 4,
      width: CONTENT_W,
      height: lineH + 8,
      color: _rgb(0.94, 0.95, 0.98),
      borderColor: _rgb(0.15, 0.39, 0.92),
      borderWidth: 0.5
    });

    this.cursorY -= lineH;
    var safeText = _sanitizeText(text);
    try {
      this.currentPage.drawText(safeText, {
        x: MARGIN.left + 8,
        y: this.cursorY,
        size: FONT_SIZE.subjectHeading,
        font: this.font,
        color: _rgb(0.12, 0.16, 0.23)
      });
    } catch (e) {
      this._drawTextCharByChar(safeText, MARGIN.left + 8, this.cursorY, FONT_SIZE.subjectHeading, _rgb(0.12, 0.16, 0.23));
    }

    // meta tags
    if (metaTags && metaTags.length) {
      this.cursorY -= FONT_SIZE.small * LINE_HEIGHT_FACTOR + 2;
      var metaText = _sanitizeText(metaTags.join('  |  '));
      try {
        this.currentPage.drawText(metaText, {
          x: MARGIN.left + 8,
          y: this.cursorY,
          size: FONT_SIZE.small,
          font: this.font,
          color: _rgb(0.4, 0.46, 0.53)
        });
      } catch (e) { /* ignore */ }
    }

    this.cursorY -= 8;
  };

  /* 繪製申論題 */
  PdfLayoutEngine.prototype.drawEssay = function (text) {
    this._ensureSpace(FONT_SIZE.body * LINE_HEIGHT_FACTOR * 2);
    this.cursorY -= 4;
    this._drawText(text, FONT_SIZE.body, { indent: 0 });
    this.cursorY -= PARAGRAPH_GAP;
  };

  /* 繪製選擇題 */
  PdfLayoutEngine.prototype.drawMCQuestion = function (item) {
    var lineH = FONT_SIZE.body * LINE_HEIGHT_FACTOR;
    // 預估需要的空間：題幹 + 4選項 + 答案
    var estimatedHeight = lineH * (2 + item.options.length);
    this._ensureSpace(Math.min(estimatedHeight, CONTENT_H * 0.3));

    // 題號 + 題幹
    var qLabel = item.num + '. ';
    var safeLabel = _sanitizeText(qLabel);
    var labelW = this.font.widthOfTextAtSize(safeLabel, FONT_SIZE.body);
    this.cursorY -= 3;

    // 記住題號位置所在頁面，繪製後驗證
    var numPage = this.currentPage;
    var numY = this.cursorY - lineH;

    // 題幹（縮排）
    this._drawText(item.text, FONT_SIZE.body, {
      x: MARGIN.left,
      indent: labelW,
      maxWidth: CONTENT_W - labelW
    });

    // 題號繪製於題幹首行同頁（_ensureSpace 已保證首行不換頁）
    try {
      numPage.drawText(safeLabel, {
        x: MARGIN.left,
        y: numY,
        size: FONT_SIZE.body,
        font: this.font,
        color: _rgb(0.15, 0.39, 0.92)
      });
    } catch (e) { /* ignore */ }

    // 題目內圖片
    if (item.figures && item.figures.length) {
      for (var f = 0; f < item.figures.length; f++) {
        // 圖片會在非同步階段處理，此處標記
        this.cursorY -= 4;
      }
    }

    // 選項
    var optIndent = labelW + 10;
    for (var i = 0; i < item.options.length; i++) {
      var opt = item.options[i];
      var optText = opt.label + ' ' + opt.text;
      this._drawText(optText, FONT_SIZE.body, {
        x: MARGIN.left,
        indent: optIndent,
        maxWidth: CONTENT_W - optIndent
      });
    }

    // 答案
    if (item.answer) {
      this.cursorY -= 2;
      this._drawText(item.answer, FONT_SIZE.small, {
        x: MARGIN.left,
        indent: optIndent,
        color: _rgb(0.06, 0.73, 0.51)  // #10b981
      });
    }

    this.cursorY -= PARAGRAPH_GAP;
  };

  /* 繪製段落註記 */
  PdfLayoutEngine.prototype.drawNote = function (text) {
    this._drawText(text, FONT_SIZE.small, {
      color: _rgb(0.4, 0.46, 0.53)
    });
    this.cursorY -= 2;
  };

  /* 繪製段落標記 */
  PdfLayoutEngine.prototype.drawSectionMarker = function (text) {
    var lineH = FONT_SIZE.body * LINE_HEIGHT_FACTOR;
    this._ensureSpace(lineH + 10);
    this.cursorY -= 6;

    this.currentPage.drawLine({
      start: { x: MARGIN.left, y: this.cursorY },
      end: { x: MARGIN.left + 120, y: this.cursorY },
      thickness: 0.5,
      color: _rgb(0.6, 0.6, 0.6)
    });

    this._drawText(text, FONT_SIZE.body, {
      color: _rgb(0.15, 0.39, 0.92)
    });
    this.cursorY -= 4;
  };

  /* 繪製閱讀測驗段落 */
  PdfLayoutEngine.prototype.drawPassage = function (text) {
    this._ensureSpace(FONT_SIZE.body * LINE_HEIGHT_FACTOR * 2);
    var startPage = this.currentPage;
    var startY = this.cursorY;
    this._drawText(text, FONT_SIZE.body, {
      indent: 8,
      color: _rgb(0.12, 0.16, 0.23)
    });
    var endY = this.cursorY;

    // 左側邊線（僅在未跨頁時繪製，跨頁邊線會錯位）
    if (this.currentPage === startPage) {
      this.currentPage.drawLine({
        start: { x: MARGIN.left + 3, y: startY },
        end: { x: MARGIN.left + 3, y: endY },
        thickness: 2,
        color: _rgb(0.15, 0.39, 0.92)
      });
    }

    this.cursorY -= PARAGRAPH_GAP;
  };

  /* ── 2d. 圖片嵌入 ── */

  /**
   * 嵌入圖片（非同步）
   * @param {string} src
   * @returns {Promise<{image: PDFImage, width: number, height: number}|null>}
   */
  async function embedImage(pdfDoc, src) {
    try {
      var response = await fetch(src);
      if (!response.ok) return null;
      var buffer = await response.arrayBuffer();
      var bytes = new Uint8Array(buffer);

      var image;
      // 判斷圖片類型
      if (bytes[0] === 0x89 && bytes[1] === 0x50) {
        image = await pdfDoc.embedPng(bytes);
      } else if (bytes[0] === 0xFF && bytes[1] === 0xD8) {
        image = await pdfDoc.embedJpg(bytes);
      } else {
        // 嘗試 PNG
        try {
          image = await pdfDoc.embedPng(bytes);
        } catch (e) {
          try {
            image = await pdfDoc.embedJpg(bytes);
          } catch (e2) {
            return null;
          }
        }
      }

      var dims = image.scale(1);
      return { image: image, width: dims.width, height: dims.height };
    } catch (e) {
      return null;
    }
  }

  PdfLayoutEngine.prototype.drawImage = async function (imgData) {
    if (!imgData) return;

    var maxW = CONTENT_W - 20;
    var maxH = CONTENT_H * 0.4;
    var w = imgData.width;
    var h = imgData.height;

    // 縮放
    if (w > maxW) {
      var scale = maxW / w;
      w *= scale;
      h *= scale;
    }
    if (h > maxH) {
      var scale2 = maxH / h;
      w *= scale2;
      h *= scale2;
    }

    this._ensureSpace(h + 10);
    this.cursorY -= h + 5;

    var x = MARGIN.left + (CONTENT_W - w) / 2;  // 置中
    this.currentPage.drawImage(imgData.image, {
      x: x,
      y: this.cursorY,
      width: w,
      height: h
    });

    this.cursorY -= 5;
  };

  PdfLayoutEngine.prototype.drawFigurePlaceholder = function (altText) {
    this._drawText('[' + (altText || '圖片') + ']', FONT_SIZE.small, {
      color: _rgb(0.6, 0.6, 0.6)
    });
    this.cursorY -= 4;
  };

  /* ── 主要產生函式 ── */

  /**
   * 產生 PDF
   * @param {{years: string[], subjects: string[]}} selection
   * @param {boolean} includeAnswers
   * @param {function(number, string)} onProgress - (percent, message)
   * @returns {Promise<{bytes: Uint8Array, filename: string}>}
   */
  async function generatePdf(selection, includeAnswers, onProgress) {
    var progress = onProgress || function () {};
    progress(0, '正在載入字型...');

    var PDFLib = window.PDFLib;
    if (!PDFLib) throw new Error('pdf-lib 未載入');

    var pdfDoc = await PDFLib.PDFDocument.create();
    pdfDoc.registerFontkit(window.fontkit);

    // 載入字型
    var fontUrl = _getFontUrl();
    progress(5, '正在下載字型...');
    var fontResponse = await fetch(fontUrl);
    if (!fontResponse.ok) throw new Error('字型載入失敗');
    var fontBytes = await fontResponse.arrayBuffer();
    progress(15, '正在嵌入字型...');
    var font = await pdfDoc.embedFont(fontBytes, { subset: true });

    // 擷取資料
    progress(20, '正在擷取試題資料...');
    var examData = extractExamData(selection, includeAnswers);
    if (!examData.length) throw new Error('未找到任何試題資料');

    // 計算總項目數（用於進度計算）
    var totalItems = 0;
    examData.forEach(function (y) {
      y.subjects.forEach(function (s) {
        totalItems += s.contentItems.length + 1; // +1 for subject heading
      });
    });
    var processedItems = 0;

    // 建立版面引擎
    var engine = new PdfLayoutEngine(pdfDoc, font, onProgress);

    // 取得頁面標題
    var pageTitleEl = document.querySelector('.page-title');
    var pageTitle = pageTitleEl ? pageTitleEl.textContent.trim() : '考古題';
    engine.headerTitle = pageTitle;
    engine.headerDate = new Date().toLocaleDateString('zh-TW');

    // 第一頁 — 封面
    engine._newPage();
    engine.cursorY -= 40;
    engine._drawText(pageTitle, FONT_SIZE.title, {
      color: _rgb(0.15, 0.39, 0.92)
    });
    engine.cursorY -= 8;

    var yearRange = selection.years.join(', ') + '年';
    var answerText = includeAnswers ? '含答案' : '不含答案';
    var subtitle = yearRange + '  |  ' + answerText + '  |  ' + engine.headerDate;
    engine._drawText(subtitle, FONT_SIZE.body, {
      color: _rgb(0.4, 0.46, 0.53)
    });
    engine.cursorY -= 20;

    progress(25, '正在產生 PDF...');

    // 逐年度、逐科目繪製
    for (var yi = 0; yi < examData.length; yi++) {
      var yearData = examData[yi];
      engine.drawYearHeading(yearData.year);

      for (var si = 0; si < yearData.subjects.length; si++) {
        var subject = yearData.subjects[si];
        engine.drawSubjectHeading(subject.name, subject.metaTags);
        processedItems++;

        for (var ci = 0; ci < subject.contentItems.length; ci++) {
          var item = subject.contentItems[ci];

          switch (item.type) {
            case 'note':
              engine.drawNote(item.text);
              break;
            case 'section-marker':
              engine.drawSectionMarker(item.text);
              break;
            case 'essay':
              engine.drawEssay(item.text);
              break;
            case 'mc-question':
              engine.drawMCQuestion(item);
              // 嵌入題目內圖片
              if (item.figures && item.figures.length) {
                for (var fi = 0; fi < item.figures.length; fi++) {
                  var imgData = await embedImage(pdfDoc, item.figures[fi].src);
                  if (imgData) {
                    await engine.drawImage(imgData);
                  } else {
                    engine.drawFigurePlaceholder(item.figures[fi].alt);
                  }
                }
              }
              break;
            case 'figure':
              var figData = await embedImage(pdfDoc, item.src);
              if (figData) {
                await engine.drawImage(figData);
              } else {
                engine.drawFigurePlaceholder(item.alt);
              }
              break;
            case 'passage':
              engine.drawPassage(item.text);
              break;
          }

          processedItems++;
          var pct = 25 + Math.round((processedItems / totalItems) * 65);
          progress(Math.min(pct, 90), '正在產生 PDF... (' + processedItems + '/' + totalItems + ')');
        }
      }
    }

    // 繪製最後一頁的頁尾
    engine._drawPageFooter();

    // 產生 PDF bytes
    progress(92, '正在組裝 PDF...');
    var pdfBytes = await pdfDoc.save();
    progress(98, '準備下載...');

    // 產生檔名
    var filename = _buildFilename(pageTitle, selection.years, includeAnswers);

    return { bytes: pdfBytes, filename: filename };
  }

  /* ── 2e. PDF 下載投遞 ── */

  /**
   * 投遞 PDF 給使用者
   * @param {Uint8Array} pdfBytes
   * @param {string} filename
   */
  async function deliverPdf(pdfBytes, filename) {
    var blob = new Blob([pdfBytes], { type: 'application/pdf' });

    // 策略 1：Web Share API（iOS 原生分享）
    if (navigator.share && navigator.canShare) {
      var file = new File([blob], filename, { type: 'application/pdf' });
      if (navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: filename });
          return;
        } catch (e) {
          if (e.name === 'AbortError') return; // 使用者取消
          // 降級到策略 2
        }
      }
    }

    // 策略 2：Blob URL + <a download>
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();

    setTimeout(function () {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 5000);
  }

  /* ── 工具函式 ── */

  function _rgb(r, g, b) {
    return window.PDFLib.rgb(r, g, b);
  }

  function _sanitizeText(text) {
    if (!text) return '';
    return text
      .replace(/\t/g, '    ')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, ' ')
      .replace(/[\uFEFF\uFFFE\uFFFF]/g, '')           // BOM & specials
      .replace(/[\u2028\u2029]/g, '\n')                // Unicode line/paragraph separators
      .replace(/[\uD800-\uDFFF]/g, ' ');               // lone surrogates
  }

  function _getFontUrl() {
    var fontName = 'fonts/NotoSansTC-Regular-subset.otf';
    // 策略 1：從 app.js 的 script 標籤推算基礎路徑
    var scripts = document.querySelectorAll('script[src*="app.js"]');
    if (scripts.length) {
      var src = scripts[0].getAttribute('src');
      // 處理各種路徑格式：../js/app.js, js/app.js, /js/app.js
      var base = src.replace(/js\/app\.js.*$/, '');
      if (base) return base + fontName;
    }
    // 策略 2：從 <link> 標籤推算
    var links = document.querySelectorAll('link[href*="style.css"]');
    if (links.length) {
      var href = links[0].getAttribute('href');
      var base2 = href.replace(/css\/style\.css.*$/, '');
      if (base2) return base2 + fontName;
    }
    // 策略 3：固定相對路徑
    return '../' + fontName;
  }

  function _buildFilename(title, years, includeAnswers) {
    var name = title.replace(/[/\\?%*:|"<>]/g, '_').replace(/\s+/g, '_');
    var yearRange = '';
    if (years.length === 1) {
      yearRange = years[0];
    } else if (years.length > 1) {
      var sorted = years.slice().sort(function (a, b) { return parseInt(a) - parseInt(b); });
      yearRange = sorted[0] + '-' + sorted[sorted.length - 1];
    }
    var answerSuffix = includeAnswers ? '含答案' : '不含答案';
    return name + '_' + yearRange + '年_' + answerSuffix + '.pdf';
  }

  /* ── 匯出公開 API ── */
  window.PdfExport = {
    generatePdf: generatePdf,
    deliverPdf: deliverPdf,
    extractExamData: extractExamData
  };

})(window);
