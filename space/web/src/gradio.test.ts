import assert from 'node:assert/strict'
import { test } from 'node:test'
import { citationId, linkCitations, parseSources, splitReply } from './gradio.ts'

test('splitReply keeps a progress-only assistant message as text', () => {
  assert.deepEqual(
    splitReply([
      { role: 'user', content: '問題' },
      { role: 'assistant', content: '已完成檢索，正在整理回答…' },
    ]),
    { text: '已完成檢索，正在整理回答…', sources: null },
  )
})

test('splitReply separates the answer and current-turn sources', () => {
  assert.deepEqual(
    splitReply([
      { role: 'user', content: '問題' },
      { role: 'assistant', content: '回答第一段' },
      { role: 'assistant', content: '回答第二段' },
      {
        role: 'assistant',
        content: '來源 markdown',
        metadata: { title: '本輪參考來源' },
      },
    ]),
    {
      text: '回答第一段\n\n回答第二段',
      sources: { title: '本輪參考來源', content: '來源 markdown' },
    },
  )
})

test('splitReply excludes sources belonging to earlier turns', () => {
  assert.deepEqual(
    splitReply([
      { role: 'user', content: '舊問題' },
      {
        role: 'assistant',
        content: '舊來源',
        metadata: { title: '舊來源區塊' },
      },
      { role: 'assistant', content: '舊回答' },
      { role: 'user', content: '新問題' },
      { role: 'assistant', content: '新回答' },
    ]),
    { text: '新回答', sources: null },
  )
})

test('splitReply returns empty text without assistant messages', () => {
  assert.deepEqual(splitReply([{ role: 'user', content: '問題' }]), {
    text: '',
    sources: null,
  })
})

test('parseSources splits the sources block into cited items', () => {
  const block = [
    '[題1]', '1. Q-1 [choice]', '題幹：甲', '',
    '## 相關現行條文', '', '[條1]', '', '警察職權行使法 第 6 條', '', '條文內容',
    '', '[條2]', '', '刑法 第 1 條',
  ].join('  \n')
  const items = parseSources(block)
  assert.deepEqual(Object.keys(items), ['題1', '條1', '條2'])
  assert.match(items['題1'], /題幹：甲/)
  assert.doesNotMatch(items['題1'], /相關現行條文|警察職權/)
  assert.match(items['條1'], /條文內容/)
  assert.doesNotMatch(items['條1'], /刑法/)
})

test('linkCitations turns citations into source links', () => {
  assert.equal(
    linkCitations('依規定[條2]，答案為[題1](A)。[其他]'),
    '依規定[條2](#src-條2)，答案為[題1](#src-題1)(A)。[其他]',
  )
})

test('citationId accepts only citation links and never throws', () => {
  assert.equal(citationId('#src-%E6%A2%9D2'), '條2')
  assert.equal(citationId('#src-題1'), '題1')
  assert.equal(citationId('#src-網1'), '網1')
  for (const href of ['#src-%E6', '#src-%ZZ', '#src-x', 'https://example.com', undefined]) {
    assert.equal(citationId(href), '')
  }
})

test('web citations are parsed and linked like exam and law citations', () => {
  assert.deepEqual(parseSources('## 網路搜尋結果（非官方來源）\n\n[網1]\n\n標題'), {
    網1: '\n標題\n',
  })
  assert.equal(linkCitations('參考[網1]。'), '參考[網1](#src-網1)。')
})
