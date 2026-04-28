import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

test('config recommendation panel does not render redundant candidate preview list', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')

  assert.equal(source.includes('class="candidate-groups"'), false)
  assert.equal(source.includes('configCandidateGroups'), false)
})
