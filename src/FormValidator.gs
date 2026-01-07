/**
 * ============================================================================
 * Google Forms 自動化 Web App
 * ============================================================================
 * 部署為 Web App 後可透過 URL 直接觸發，無需手動執行
 */

/**
 * Web App 入口點 - GET 請求
 */
function doGet(e) {
  var action = e.parameter.action || 'status';
  var result = {};
  
  try {
    switch (action) {
      case 'create':
        result = createFormFromCSV();
        break;
      case 'validate':
        result = validateAllForms();
        break;
      case 'list':
        result = listAllForms();
        break;
      case 'status':
        result = { status: 'ok', message: 'Web App 運作正常', timestamp: new Date().toISOString() };
        break;
      default:
        result = { error: '未知的 action: ' + action };
    }
  } catch (err) {
    result = { error: err.message, stack: err.stack };
  }
  
  return ContentService
    .createTextOutput(JSON.stringify(result, null, 2))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Web App 入口點 - POST 請求
 */
function doPost(e) {
  return doGet(e);
}

/**
 * 列出所有表單 (JSON 格式)
 */
function listAllForms() {
  var results = [];
  var files = DriveApp.getFilesByType(MimeType.GOOGLE_FORMS);
  
  while (files.hasNext()) {
    var file = files.next();
    var name = file.getName();
    
    if (name.indexOf('警察') > -1 || name.indexOf('情境實務') > -1 || name.indexOf('考古題') > -1) {
      try {
        var form = FormApp.openById(file.getId());
        var items = form.getItems();
        var mcCount = 0;
        
        for (var i = 0; i < items.length; i++) {
          if (items[i].getType() === FormApp.ItemType.MULTIPLE_CHOICE) {
            mcCount++;
          }
        }
        
        results.push({
          name: name,
          questionCount: mcCount,
          publishedUrl: form.getPublishedUrl(),
          editUrl: form.getEditUrl(),
          status: 'ok'
        });
      } catch (err) {
        results.push({
          name: name,
          status: 'error',
          error: err.message
        });
      }
    }
  }
  
  return {
    timestamp: new Date().toISOString(),
    count: results.length,
    forms: results
  };
}

/**
 * 驗證所有表單 (JSON 格式)
 */
function validateAllForms() {
  var results = {
    timestamp: new Date().toISOString(),
    summary: { total: 0, passed: 0, failed: 0 },
    forms: []
  };
  
  var files = DriveApp.getFilesByType(MimeType.GOOGLE_FORMS);
  
  while (files.hasNext()) {
    var file = files.next();
    var name = file.getName();
    
    if (name.indexOf('警察') > -1 || name.indexOf('情境實務') > -1 || name.indexOf('考古題') > -1) {
      var formResult = {
        name: name,
        id: file.getId(),
        status: 'PASS',
        questionCount: 0,
        issues: [],
        editUrl: '',
        publishedUrl: ''
      };
      
      try {
        var form = FormApp.openById(file.getId());
        formResult.editUrl = form.getEditUrl();
        formResult.publishedUrl = form.getPublishedUrl();
        
        var items = form.getItems();
        var mcCount = 0;
        
        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          if (item.getType() === FormApp.ItemType.MULTIPLE_CHOICE) {
            mcCount++;
            var mcItem = item.asMultipleChoiceItem();
            var choices = mcItem.getChoices();
            
            if (choices.length < 2) {
              formResult.issues.push('題目 ' + (mcCount) + ' 選項不足');
              formResult.status = 'FAIL';
            }
            
            var hasCorrect = false;
            for (var j = 0; j < choices.length; j++) {
              if (choices[j].isCorrectAnswer()) {
                hasCorrect = true;
                break;
              }
            }
            if (!hasCorrect) {
              formResult.issues.push('題目 ' + (mcCount) + ' 無正確答案');
              formResult.status = 'FAIL';
            }
          }
        }
        
        formResult.questionCount = mcCount;
        
        if (mcCount === 0) {
          formResult.status = 'FAIL';
          formResult.issues.push('無題目');
        }
        
      } catch (err) {
        formResult.status = 'FAIL';
        formResult.issues.push('無法開啟: ' + err.message);
      }
      
      results.forms.push(formResult);
      results.summary.total++;
      
      if (formResult.status === 'PASS') {
        results.summary.passed++;
      } else {
        results.summary.failed++;
      }
    }
  }
  
  // 也輸出到 console
  console.log('========================================');
  console.log('       驗證結果');
  console.log('========================================');
  console.log('總數: ' + results.summary.total);
  console.log('通過: ' + results.summary.passed);
  console.log('失敗: ' + results.summary.failed);
  
  for (var k = 0; k < results.forms.length; k++) {
    var f = results.forms[k];
    var icon = f.status === 'PASS' ? '[OK]' : '[FAIL]';
    console.log((k+1) + '. ' + icon + ' ' + f.name + ' (' + f.questionCount + '題)');
    console.log('   ' + f.publishedUrl);
  }
  
  return results;
}

/**
 * 快速測試
 */
function quickTest() {
  console.log('開始快速測試...');
  
  var files = DriveApp.getFilesByType(MimeType.GOOGLE_FORMS);
  var count = 0;
  
  while (files.hasNext() && count < 10) {
    var file = files.next();
    count++;
    console.log(count + '. ' + file.getName());
  }
  
  console.log('找到 ' + count + ' 個表單');
  return count;
}
