import assert from 'node:assert/strict'
import test from 'node:test'

import { buildCandidateGroups, formatStaggerCandidate } from '../src/candidates.js'

test('stagger candidate labels avoid confusing zero-minute wording', () => {
  assert.equal(formatStaggerCandidate(0), '不启用')
  assert.equal(formatStaggerCandidate(10), '10 分钟')
})

test('candidate groups keep window seat and stagger options separated', () => {
  const groups = buildCandidateGroups([4, 5, 6], [120, 140, 160], [0, 5, 10])

  assert.deepEqual(groups.map((group) => group.label), ['窗口', '座位', '错峰'])
  assert.deepEqual(groups[0].values, ['4 个', '5 个', '6 个'])
  assert.deepEqual(groups[1].values, ['120 个', '140 个', '160 个'])
  assert.deepEqual(groups[2].values, ['不启用', '5 分钟', '10 分钟'])
})
