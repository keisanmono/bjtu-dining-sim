// 文件说明：图表渲染前置条件测试，验证零尺寸容器不会初始化 ECharts。

import assert from 'node:assert/strict'
import test from 'node:test'

import { canRenderChartElement } from '../src/chartUtils.js'

// 验证隐藏或零尺寸图表容器不会触发 ECharts 渲染。
test('hidden chart containers are not renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 0, clientHeight: 260 }), false)
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 0 }), false)
})

// 验证宽高都存在的容器可以安全初始化图表。
test('visible chart containers are renderable', () => {
  assert.equal(canRenderChartElement({ clientWidth: 420, clientHeight: 260 }), true)
})
