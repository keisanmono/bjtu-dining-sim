// 文件说明：前端源码文件。

import assert from 'node:assert/strict'
import test from 'node:test'

import { canRenderChartElement } from '../src/chartUtils.js'

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('hidden chart containers are not renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 0, clientHeight: 260 }), false)
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 0 }), false)
})

// 讲解注释：测试用例 封装本文件中的一个独立处理步骤。
test('visible chart containers are renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 260 }), true)
})
