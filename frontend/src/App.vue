<!-- 文件说明：前端主页面：组织配置、场景、实时运行、结果分析和推荐交互。 -->

<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">20 组</p>
        <h1>北京交通大学就餐仿真系统</h1>
      </div>
      <div class="topbar-actions">
        <el-tag :type="healthOk ? 'success' : 'warning'" effect="light">{{ healthText }}</el-tag>
        <el-button :icon="Refresh" circle @click="checkHealth" />
      </div>
    </header>

    <el-tabs v-model="activeView" class="stage-tabs" @tab-change="renderCharts">
      <el-tab-pane label="参数配置" name="config" />
      <el-tab-pane label="场景预览" name="layout" />
      <el-tab-pane label="实时运行" name="run" />
      <el-tab-pane label="结果分析" name="analysis" />
      <el-tab-pane label="记录页" name="records" />
    </el-tabs>

    <main>
      <section v-show="activeView === 'config'" class="config-grid">
        <div class="config-sidebar">
          <el-card class="panel config-basic-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Setting /></el-icon>
              <span>基础参数</span>
            </div>
          </template>
          <el-form label-position="top" :model="config" class="config-form">
            <div v-if="arrivalMode === 'manual'" class="config-section manual-arrival-section">
              <div class="config-section-title">手动到达</div>
              <div class="config-field-grid">
                <el-form-item label="平均每分钟到达人数">
                  <el-input-number v-model="config.arrival_rate" :min="0.1" :step="0.5" controls-position="right" />
                </el-form-item>
                <el-form-item label="到达持续时间">
                  <el-input-number v-model="config.duration_min" :min="5" :max="360" controls-position="right" />
                </el-form-item>
                <el-form-item label="错峰分钟">
                  <el-input-number v-model="config.stagger_minutes" :min="0" :max="120" controls-position="right" />
                </el-form-item>
                <el-form-item label="高峰开始">
                  <el-input-number v-model="config.peak_start_min" :min="0" controls-position="right" />
                </el-form-item>
                <el-form-item label="高峰结束">
                  <el-input-number v-model="config.peak_end_min" :min="0" controls-position="right" />
                </el-form-item>
              </div>
            </div>

            <div class="config-section service-random-section">
              <div class="config-section-title">服务与随机性</div>
              <div class="config-field-grid">
              <el-form-item label="平均打饭时长（分钟）">
                <el-input-number v-model="config.service_time_mean" :min="0.05" :step="0.05" controls-position="right" />
                </el-form-item>
                <el-form-item label="平均就餐时长">
                  <el-input-number v-model="config.dining_time_mean" :min="1" :step="1" controls-position="right" />
                </el-form-item>
                <el-form-item label="随机种子">
                  <el-input-number v-model="config.seed" :min="1" controls-position="right" />
                </el-form-item>
                <el-form-item label="仿真质量">
                  <el-select v-model="config.movement_quality_preset" @change="applyMovementQualityPreset">
                    <el-option label="快速" value="fast" />
                    <el-option label="平衡" value="balanced" />
                    <el-option label="质量" value="quality" />
                  </el-select>
                </el-form-item>
                <el-form-item label="移动 tick 秒">
                  <el-input-number v-model="config.movement_tick_seconds" :min="1" :max="15" controls-position="right" />
                </el-form-item>
                <el-form-item label="网格边长">
                  <el-input-number v-model="config.floor_cell_size" :min="4" :step="2" controls-position="right" />
                </el-form-item>
              </div>
            </div>
          </el-form>

          <div class="button-row config-action-bar">
            <el-button :icon="CircleCheck" @click="validateConfig">参数校验</el-button>
            <el-button :icon="Refresh" @click="loadDefault">加载默认场景</el-button>
            <el-button type="primary" :icon="VideoPlay" @click="startLiveRun">开始仿真</el-button>
          </div>

          <el-alert
            v-if="validationMessage"
            class="validation-alert"
            :type="validationType"
            :title="validationMessage"
            show-icon
            :closable="false"
          />
        </el-card>

        <el-card class="panel recommendation-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><MagicStick /></el-icon>
              <span>优化推荐</span>
            </div>
          </template>
          <div class="candidate-block">
            <div class="candidate-editor">
              <div class="candidate-range-grid">
                <div class="candidate-editor-row">
                  <span>窗口</span>
                  <el-input-number v-model="candidateSettings.windowMin" :min="1" :max="30" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.windowMax" :min="1" :max="30" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row">
                  <span>座位</span>
                  <el-input-number v-model="candidateSettings.seatMin" :min="2" :max="layoutSeatLimit" :step="2" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.seatMax" :min="2" :max="layoutSeatLimit" :step="2" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row candidate-editor-row-single">
                  <span>座位步长</span>
                  <el-input-number v-model="candidateSettings.seatStep" :min="2" :max="200" :step="2" size="small" controls-position="right" />
                  <span class="range-hint">候选间隔</span>
                </div>
                <div class="candidate-editor-row">
                  <span>错峰</span>
                  <el-input-number v-model="candidateSettings.staggerMin" :min="0" :max="120" :step="5" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.staggerMax" :min="0" :max="120" :step="5" size="small" controls-position="right" />
                </div>
                <div class="candidate-editor-row candidate-editor-row-single">
                  <span>错峰步长</span>
                  <el-input-number v-model="candidateSettings.staggerStep" :min="1" :max="60" :step="5" size="small" controls-position="right" />
                  <span class="range-hint">候选间隔</span>
                </div>
                <div class="candidate-editor-row">
                  <span>下课峰数</span>
                  <el-input-number v-model="candidateSettings.peakCountMin" :min="1" :max="6" size="small" controls-position="right" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="candidateSettings.peakCountMax" :min="1" :max="6" size="small" controls-position="right" />
                </div>
              </div>
              <div class="candidate-actions">
                <el-button size="small" :icon="Refresh" @click="resetCandidateSettings">按当前参数重置范围</el-button>
                <el-button type="primary" size="small" :icon="MagicStick" :loading="isRecommending" @click="generateRecommendation">生成推荐</el-button>
              </div>
            </div>

            <el-divider />
            <el-empty v-if="!recommendation" description="暂无推荐结果" />
            <template v-else>
              <div class="config-recommend-summary">
                <div class="recommend-result-item wide">
                  <div class="recommend-result-heading">
                    <div>
                      <p>推荐配置</p>
                      <strong>{{ formatConfigSummary(recommendation.best.config) }}</strong>
                    </div>
                    <el-button type="success" size="small" :icon="CircleCheck" @click="applyRecommendationConfig(recommendation.best.config)">
                      应用推荐方案
                    </el-button>
                  </div>
                </div>
                <div class="recommend-result-item">
                  <p>平均等待</p>
                  <strong>{{ formatMinutes(recommendation.best.metrics.avg_wait) }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>峰值排队</p>
                  <strong>{{ recommendation.best.metrics.peak_queue }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>完成就餐</p>
                  <strong>{{ recommendation.best.metrics.throughput }}</strong>
                </div>
                <div class="recommend-result-item">
                  <p>评分</p>
                  <strong>{{ formatNumber(recommendation.best.score) }}</strong>
                </div>
              </div>
              <p class="explain-text compact">{{ explanation?.text || recommendation.explanation_summary }}</p>
              <el-table :data="recommendation.ranking" class="config-effect-table" size="small" height="260">
                <el-table-column label="方案" min-width="130">
                  <template #default="{ row }">{{ row.strategy }}</template>
                </el-table-column>
                <el-table-column label="配置" min-width="130">
                  <template #default="{ row }">{{ formatConfigSummary(row.config) }}</template>
                </el-table-column>
                <el-table-column label="平均等待" width="92">
                  <template #default="{ row }">{{ formatMinutes(row.metrics.avg_wait) }}</template>
                </el-table-column>
                <el-table-column label="峰值排队" width="86">
                  <template #default="{ row }">{{ row.metrics.peak_queue }}</template>
                </el-table-column>
                <el-table-column label="完成就餐" width="90">
                  <template #default="{ row }">{{ row.metrics.throughput }}</template>
                </el-table-column>
                <el-table-column label="评分" width="74">
                  <template #default="{ row }">{{ formatNumber(row.score) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="92" fixed="right">
                  <template #default="{ row }">
                    <el-button type="primary" size="small" plain @click="applyRecommendationConfig(row.config)">应用方案</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </template>
          </div>
        </el-card>
        </div>

        <el-card class="panel campus-panel">
          <template #header>
            <div class="panel-title">
              <el-icon><Grid /></el-icon>
              <span>校园到达</span>
            </div>
          </template>
          <el-form label-position="top" class="campus-form">
            <div class="campus-mode-strip">
              <el-form-item label="到达模式">
                <el-radio-group v-model="arrivalMode">
                  <el-radio-button label="manual">手动平均</el-radio-button>
                  <el-radio-button label="campus">校园人数</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </div>

            <template v-if="arrivalMode === 'campus'">
              <div class="campus-toolbar">
                <el-form-item label="目标食堂">
                  <el-select v-model="selectedCafeteriaId" placeholder="选择食堂">
                    <el-option
                      v-for="cafeteria in campusCafeterias"
                      :key="cafeteria.id"
                      :label="cafeteria.name"
                      :value="cafeteria.id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="就餐时段">
                  <el-select v-model="config.meal_period" @change="applyMealPeriodDefaults">
                    <el-option label="早餐" value="breakfast" />
                    <el-option label="午餐" value="lunch" />
                    <el-option label="晚餐" value="dinner" />
                    <el-option label="周末" value="weekend" />
                  </el-select>
                </el-form-item>
                <el-form-item label="人数来源" class="campus-source-field">
                  <el-tag effect="light">{{ campusSourceLabel }}</el-tag>
                </el-form-item>
                <div class="campus-actions">
                  <el-button
                    :icon="Refresh"
                    :loading="campusLoadingSource === 'live'"
                    :disabled="campusLoadingSource !== '' && campusLoadingSource !== 'live'"
                    @click="loadCampusOccupancy('live')"
                  >
                    获取实时数据
                  </el-button>
                  <el-button
                    :icon="MagicStick"
                    :loading="campusLoadingSource === 'random'"
                    :disabled="campusLoadingSource !== '' && campusLoadingSource !== 'random'"
                    @click="loadCampusOccupancy('random')"
                  >
                    随机生成
                  </el-button>
                  <el-button
                    :icon="Tickets"
                    :loading="campusRecordSaving"
                    :disabled="campusLoadingSource !== ''"
                    @click="saveCampusArrivalRecord()"
                  >
                    保存当前记录
                  </el-button>
                </div>
              </div>

              <el-alert
                v-if="campusWarning"
                class="validation-alert"
                type="warning"
                :title="campusWarning"
                show-icon
                :closable="false"
              />

              <el-tabs v-model="campusSourceTab" class="campus-source-tabs">
                <el-tab-pane label="教学楼实时人数" name="teaching">
                  <el-table :data="campusRows" class="campus-table" size="small" height="420">
                    <el-table-column label="教学楼" min-width="128">
                      <template #default="{ row }">{{ row.building_name }}</template>
                    </el-table-column>
                    <el-table-column label="下课时间" width="112">
                      <template #default="{ row }">
                        <el-input v-model="row.dismissal_time" size="small" placeholder="11:30" @change="syncDismissalTime(row)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="就餐比例" width="120">
                      <template #default="{ row }">
                        <div class="percent-input">
                          <el-input-number v-model="row.release_percent" :min="0" :max="100" :step="5" size="small" controls-position="right" />
                          <span class="percent-suffix">%</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="选择概率" width="124">
                      <template #default="{ row }">
                        <div class="percent-input">
                          <el-input-number
                            :model-value="campusTableChoicePercent(row)"
                            :min="0"
                            :max="100"
                            :step="5"
                            size="small"
                            controls-position="right"
                            @update:model-value="updateCampusRowChoicePercent(row, $event)"
                          />
                          <span class="percent-suffix">%</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="路程" width="78">
                      <template #default="{ row }">{{ campusTableWalkMinutes(row) }} min</template>
                    </el-table-column>
                    <el-table-column label="人数（教学楼可手动填写）" min-width="280">
                      <template #default="{ row }">
                        <div class="floor-inputs">
                          <label v-for="floor in row.floors" :key="`${row.building_id}-${floor.floor}`" class="floor-input">
                            <span>{{ floor.floor }}F</span>
                            <el-input-number v-model="floor.count" :min="0" :max="999" size="small" controls-position="right" />
                          </label>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="到达人数" width="88">
                      <template #default="{ row }">{{ campusTablePopulationLabel(row) }}</template>
                    </el-table-column>
                  </el-table>
                </el-tab-pane>

                <el-tab-pane label="宿舍人口反推" name="residential">
                  <div class="campus-population-controls">
                    <div class="config-section-title">人口池与宿舍释放</div>
                    <div class="campus-population-control-grid">
                      <el-form-item label="潜在人群池">
                        <el-input-number v-model="campusPopulationPoolForm.total_population_pool" :min="0" :step="500" size="small" controls-position="right" />
                      </el-form-item>
                      <el-form-item label="食堂参与率">
                        <div class="percent-input">
                          <el-input-number v-model="campusPopulationPoolForm.meal_participation_percent" :min="0" :max="100" :step="5" size="small" controls-position="right" />
                          <span class="percent-suffix">%</span>
                        </div>
                      </el-form-item>
                      <el-form-item label="其他已知来源">
                        <el-input-number v-model="campusPopulationPoolForm.other_known_population" :min="0" :step="100" size="small" controls-position="right" />
                      </el-form-item>
                      <el-form-item label="宿舍参与率">
                        <div class="percent-input">
                          <el-input-number v-model="campusResidentialProfileForm.residential_participation_percent" :min="0" :max="100" :step="5" size="small" controls-position="right" />
                          <span class="percent-suffix">%</span>
                        </div>
                      </el-form-item>
                      <el-form-item label="宿舍开始">
                        <el-input v-model="campusResidentialProfileForm.start_time" size="small" placeholder="11:00" />
                      </el-form-item>
                      <el-form-item label="宿舍结束">
                        <el-input v-model="campusResidentialProfileForm.end_time" size="small" placeholder="13:00" />
                      </el-form-item>
                      <el-form-item label="宿舍峰值">
                        <el-input v-model="campusResidentialProfileForm.peak_time" size="small" placeholder="12:00" />
                      </el-form-item>
                    </div>
                  </div>

                  <el-table :data="campusResidentialAreaSummaryRows" class="campus-table campus-residential-summary" size="small">
                    <el-table-column label="片区" min-width="110">
                      <template #default="{ row }">{{ row.campus_area }}</template>
                    </el-table-column>
                    <el-table-column label="宿舍来源" min-width="220" show-overflow-tooltip>
                      <template #default="{ row }">{{ row.source_names }}</template>
                    </el-table-column>
                    <el-table-column label="释放窗口" width="118">
                      <template #default="{ row }">{{ row.release_window }}</template>
                    </el-table-column>
                    <el-table-column label="参与率" width="82">
                      <template #default="{ row }">{{ row.participation_label }}</template>
                    </el-table-column>
                    <el-table-column label="权重合计" width="88">
                      <template #default="{ row }">{{ formatNumber(row.capacity_weight) }}</template>
                    </el-table-column>
                    <el-table-column label="反推人口" width="94">
                      <template #default="{ row }">{{ row.population_label }}</template>
                    </el-table-column>
                    <el-table-column label="到达人数" width="94">
                      <template #default="{ row }">{{ row.arrival_population_label }}</template>
                    </el-table-column>
                  </el-table>

                  <el-collapse v-model="campusResidentialDetailPanels" class="campus-detail-collapse">
                    <el-collapse-item title="详细权重输入" name="weights">
                      <el-table :data="campusResidentialTableRows" class="campus-table" size="small" height="360">
                        <el-table-column label="宿舍" min-width="150">
                          <template #default="{ row }">{{ row.source_name }}</template>
                        </el-table-column>
                        <el-table-column label="片区" min-width="110">
                          <template #default="{ row }">{{ row.campus_area }}</template>
                        </el-table-column>
                        <el-table-column label="释放窗口" width="118">
                          <template #default="{ row }">{{ row.release_window }}</template>
                        </el-table-column>
                        <el-table-column label="参与率" width="86">
                          <template #default>{{ formatPercent(residentialParticipationRate) }}</template>
                        </el-table-column>
                        <el-table-column label="选择概率" width="124">
                          <template #default="{ row }">
                            <div class="percent-input">
                              <el-input-number
                                :model-value="campusTableChoicePercent(row)"
                                :min="0"
                                :max="100"
                                :step="5"
                                size="small"
                                controls-position="right"
                                @update:model-value="updateResidentialChoicePercent(row.source_id, $event)"
                              />
                              <span class="percent-suffix">%</span>
                            </div>
                          </template>
                        </el-table-column>
                        <el-table-column label="路程" width="78">
                          <template #default="{ row }">{{ campusTableWalkMinutes(row) }} min</template>
                        </el-table-column>
                        <el-table-column label="反推人口" min-width="150">
                          <template #default="{ row }">
                            <div class="campus-readonly-source">
                              <strong>{{ row.population_label }}</strong>
                              <span>{{ row.basis }}</span>
                            </div>
                          </template>
                        </el-table-column>
                        <el-table-column label="权重" width="138">
                          <template #default="{ row }">
                            <label class="campus-weight-input">
                              <span>权重</span>
                              <el-input-number
                                :model-value="residentialCapacityWeight(row.source_id)"
                                :min="0"
                                :step="0.5"
                                size="small"
                                controls-position="right"
                                @update:model-value="updateResidentialCapacityWeight(row.source_id, $event)"
                              />
                            </label>
                          </template>
                        </el-table-column>
                        <el-table-column label="到达人数" width="94">
                          <template #default="{ row }">{{ campusTablePopulationLabel(row) }}</template>
                        </el-table-column>
                      </el-table>
                    </el-collapse-item>
                  </el-collapse>
                </el-tab-pane>
              </el-tabs>
            </template>
          </el-form>
        </el-card>
      </section>

      <section v-show="activeView === 'layout'" class="layout-page">
        <el-card class="panel layout-page-panel">
          <template #header>
            <div class="panel-title layout-panel-title">
              <span class="panel-title-main">
                <el-icon><Grid /></el-icon>
                <span>仿真场景预览</span>
              </span>
              <el-button type="primary" plain :icon="MagicStick" @click="optimizeCurrentLayout">
                一键优化布局
              </el-button>
            </div>
          </template>
          <LayoutEditor
            :layout="layout"
            :seat-limit="layoutSeatLimit"
            :window-count="config.num_windows"
            :seat-count="config.num_seats"
            @update:layout="onLayoutUpdate"
            @update:window-count="updateWindowCount"
            @update:seat-count="updateSeatCount"
            @reset="resetLayout"
          />
        </el-card>
      </section>

      <section v-show="activeView === 'run'" class="run-layout">
        <el-card class="panel run-controls">
          <div class="control-row">
            <el-button type="success" :icon="VideoPlay" :disabled="isRunning" @click="startLiveRun">开始</el-button>
            <el-button type="warning" :icon="VideoPause" :disabled="!isRunning" @click="pauseRun">暂停</el-button>
            <el-button :icon="Right" :disabled="isRunning || isDone" @click="singleStep(false)">单步</el-button>
            <el-button type="danger" :icon="Refresh" @click="resetRun">重置</el-button>
            <el-button :icon="Finished" @click="runFullSimulation">快速完成</el-button>
            <el-button :icon="Download" :disabled="!runId || !metrics" @click="exportRecords">导出记录</el-button>
            <div class="time-chip">当前时刻：{{ currentClockLabel }}</div>
          </div>
        </el-card>

        <div class="metric-grid">
          <el-card v-for="card in runCards" :key="card.label" class="metric-card">
            <p>{{ card.label }}</p>
            <strong>{{ card.value }}</strong>
            <span>{{ card.hint }}</span>
          </el-card>
        </div>

        <div class="run-grid">
          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Histogram /></el-icon>
                <span>窗口排队情况</span>
              </div>
            </template>
            <div ref="queueChartEl" class="chart-box" />
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Grid /></el-icon>
                <span>实时食堂地图</span>
              </div>
            </template>
            <LiveDiningMap
              :layout="layout"
              :state="currentState"
              @transition-settled="onLiveMapTransitionSettled"
            />
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                <span>关键指标趋势</span>
              </div>
            </template>
            <div ref="trendChartEl" class="chart-box" />
          </el-card>
        </div>
      </section>

      <section v-show="activeView === 'analysis'" class="analysis-layout">
        <div class="metric-grid">
          <el-card v-for="card in analysisCards" :key="card.label" class="metric-card">
            <p>{{ card.label }}</p>
            <strong>{{ card.value }}</strong>
            <span>{{ card.hint }}</span>
          </el-card>
        </div>

        <div class="analysis-grid">
          <el-card class="panel wide-panel">
            <template #header>
              <div class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                <span>运行趋势</span>
              </div>
            </template>
            <div ref="analysisChartEl" class="chart-box large" />
          </el-card>

          <el-card class="panel">
            <template #header>
              <div class="panel-title">
                <el-icon><Tickets /></el-icon>
                <span>过程记录</span>
              </div>
            </template>
            <el-table :data="recentRecords" height="330" size="small">
              <el-table-column prop="t" label="t" width="58" />
              <el-table-column prop="arrived_count" label="到达" width="70" />
              <el-table-column prop="served_count" label="取餐" width="70" />
              <el-table-column prop="empty_seats" label="空座" width="70" />
              <el-table-column prop="available_seats" label="可用" width="70" />
              <el-table-column prop="reserved_seats" label="预留" width="70" />
              <el-table-column prop="waiting_for_seat_count" label="等座" width="70" />
              <el-table-column label="排队">
                <template #default="{ row }">{{ totalQueue(row) }}</template>
              </el-table-column>
            </el-table>
            <div class="button-row compact">
              <el-button :icon="Refresh" @click="activeView = 'config'">重新实验</el-button>
            </div>
          </el-card>
        </div>
      </section>

      <section v-show="activeView === 'records'" class="records-layout">
        <el-card class="panel records-panel">
          <template #header>
            <div class="panel-title records-panel-title">
              <span class="panel-title-main">
                <el-icon><Tickets /></el-icon>
                <span>校园到达记录</span>
              </span>
              <div class="records-toolbar">
                <el-button :icon="Refresh" :loading="campusRecordLoading" @click="loadCampusArrivalRecords">刷新记录</el-button>
                <el-button
                  type="primary"
                  :icon="Download"
                  :loading="campusRecordImporting"
                  :disabled="!selectedCampusArrivalRecords.length"
                  @click="importSelectedCampusArrivalAverage"
                >
                  导入选中平均值
                </el-button>
              </div>
            </div>
          </template>

          <el-table
            :data="campusArrivalRecords"
            row-key="record_id"
            height="520"
            size="small"
            @selection-change="onCampusRecordSelectionChange"
          >
            <el-table-column type="selection" width="46" />
            <el-table-column prop="created_at" label="记录时间" min-width="170">
              <template #default="{ row }">{{ formatCampusRecordTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="来源" width="92">
              <template #default="{ row }">{{ campusRecordSourceLabel(row.source_mode) }}</template>
            </el-table-column>
            <el-table-column label="时段" width="82">
              <template #default="{ row }">{{ mealPeriodLabel(row.meal_period) }}</template>
            </el-table-column>
            <el-table-column label="目标食堂" min-width="110">
              <template #default="{ row }">{{ cafeteriaName(row.cafeteria_id) }}</template>
            </el-table-column>
            <el-table-column label="教学楼人数" width="104">
              <template #default="{ row }">{{ formatNumber(row.teaching_population) }}</template>
            </el-table-column>
            <el-table-column label="宿舍反推" width="104">
              <template #default="{ row }">{{ formatNumber(row.residential_population) }}</template>
            </el-table-column>
            <el-table-column label="合计" width="92">
              <template #default="{ row }">{{ formatNumber(row.total_population) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="104" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" size="small" plain @click="importCampusArrivalRecord(row)">导入</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </section>

    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Download,
  Finished,
  Grid,
  Histogram,
  MagicStick,
  Refresh,
  Right,
  Setting,
  Tickets,
  TrendCharts,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'
import { api } from './api'
import { buildCandidatesFromSettings, createDefaultCandidateSettings } from './candidates'
import { canRenderChartElement } from './chartUtils'
import { buildSimulationConfigPayload } from './layout'
import {
  adjustLayoutWindowCount,
  calculateLayoutSeatLimit,
  createDefaultLayout,
  LAYOUT_DEFAULT_FLOOR,
  normalizeSeatCount,
  optimizeLayoutForFlow,
  rebuildLayoutTablesForSeats,
  totalLayoutSeats
} from './layoutEditor'
import LayoutEditor from './LayoutEditor.vue'
import LiveDiningMap from './LiveDiningMap.vue'
import { LIVE_TRANSITION_MS } from './liveMapModel'
import { applyRecommendedConfig, nextViewAfterRecommendation } from './recommendationFlow'
import { liveStepDelay, shouldRequestLiveStep, shouldResetStepRun } from './runControl'
import { clockMinuteFromRecord, formatClockMinute, parseClockTime } from './time'

// 默认仿真参数：展示时可从这里说明窗口数、座位数、到达率、服务时长、
// 就餐时长和随机种子如何组成后端 SimulationConfig。
const defaultConfig = {
  num_windows: 4,
  num_seats: 120,
  arrival_rate: 8,
  service_time_mean: 0.5,
  dining_time_mean: 20,
  duration_min: 60,
  simulation_start_minute: 660,
  meal_period: 'lunch',
  seed: 20,
  peak_start_min: 15,
  peak_end_min: 40,
  peak_multiplier: 1.4,
  stagger_minutes: 0,
  seat_columns: 12,
  campus_demand: null,
  window_choice_temperature: 0,
  window_switch_cooldown_min: 0,
  window_switch_threshold_min: 2,
  window_switch_penalty_min: 0.5,
  movement_quality_preset: 'fast',
  movement_model: 'path',
  movement_tick_seconds: 5,
  floor_cell_size: 12,
  floor_allow_diagonal: false,
  floor_static_weight: 1.0,
  floor_density_weight: 1.2,
  floor_dynamic_weight: 0.35,
  floor_wall_weight: 0.6,
  floor_inertia_weight: 0.25,
  floor_group_weight: 0.8,
  floor_randomness: 0.05,
  dynamic_field_decay: 0.85,
  dynamic_field_diffusion: 0.10,
  max_movement_ticks_per_minute: 12,
  queue_spacing_cells: 1,
  personal_space_radius_cells: 1,
  congestion_density_threshold: 3,
  advanced_movement_coupling: false,
  entry_spawn_radius_cells: 3,
  floor_width: LAYOUT_DEFAULT_FLOOR.width,
  floor_height: LAYOUT_DEFAULT_FLOOR.height
}

const movementQualityPresets = {
  fast: {
    movement_model: 'path',
    floor_cell_size: 18,
    max_movement_ticks_per_minute: 1,
    advanced_movement_coupling: false,
    window_choice_temperature: 0,
    window_switch_cooldown_min: 0
  },
  balanced: {
    movement_model: 'static_floor_field',
    floor_cell_size: 14,
    max_movement_ticks_per_minute: 1,
    advanced_movement_coupling: false,
    window_choice_temperature: 0.6,
    window_switch_cooldown_min: 0
  },
  quality: {
    movement_model: 'advanced_floor_field',
    floor_cell_size: 12,
    max_movement_ticks_per_minute: 12,
    advanced_movement_coupling: true,
    window_choice_temperature: 0.45,
    window_switch_cooldown_min: 2,
    window_switch_threshold_min: 1.5,
    window_switch_penalty_min: 0.5
  }
}

const LIVE_RECORD_LIMIT = 600
const LIVE_CHART_RECORD_LIMIT = 240
const LIVE_CHART_RENDER_INTERVAL_MS = 900
const MEAL_START_MINUTES = {
  breakfast: 420,
  lunch: 660,
  dinner: 1020,
  weekend: 510
}
const DEFAULT_POPULATION_POOL_BY_PERIOD = {
  breakfast: {
    enabled: true,
    meal_period: 'breakfast',
    total_population_pool: 12000,
    total_population_mode: 'manual',
    meal_participation_rate: 0.55,
    other_known_population: 0,
    residential_allocation_mode: 'capacity_weight',
    residual_policy: 'clamp_zero'
  },
  lunch: {
    enabled: true,
    meal_period: 'lunch',
    total_population_pool: 15000,
    total_population_mode: 'manual',
    meal_participation_rate: 0.75,
    other_known_population: 400,
    residential_allocation_mode: 'capacity_weight',
    residual_policy: 'clamp_zero'
  },
  dinner: {
    enabled: true,
    meal_period: 'dinner',
    total_population_pool: 15000,
    total_population_mode: 'manual',
    meal_participation_rate: 0.70,
    other_known_population: 500,
    residential_allocation_mode: 'capacity_weight',
    residual_policy: 'clamp_zero'
  },
  weekend: {
    enabled: true,
    meal_period: 'weekend',
    total_population_pool: 10000,
    total_population_mode: 'manual',
    meal_participation_rate: 0.50,
    other_known_population: 200,
    residential_allocation_mode: 'capacity_weight',
    residual_policy: 'clamp_zero'
  }
}
const DEFAULT_RESIDENTIAL_RELEASE_PROFILES = {
  breakfast: { meal_period: 'breakfast', start_minute: 420, end_minute: 510, peak_minute: 465, distribution: 'triangular', residential_participation_rate: 0.45 },
  lunch: { meal_period: 'lunch', start_minute: 660, end_minute: 780, peak_minute: 720, distribution: 'triangular', residential_participation_rate: 0.65 },
  dinner: { meal_period: 'dinner', start_minute: 1020, end_minute: 1140, peak_minute: 1080, distribution: 'triangular', residential_participation_rate: 0.75 },
  weekend: { meal_period: 'weekend', start_minute: 510, end_minute: 780, peak_minute: 660, distribution: 'triangular', residential_participation_rate: 0.50 }
}

// 页面级状态：activeView 控制四个页签，config/layout 保存用户配置，
// runId/records/metrics/currentState 分别对应一次运行的编号、分钟记录、
// 最终指标和地图实时状态，是展示时说明前后端数据流的主线。
const activeView = ref('config')
const config = reactive({ ...defaultConfig })
const layout = ref(createDefaultLayout(defaultConfig))
const isSyncingLayout = ref(false)
const candidateSettings = reactive(createDefaultCandidateSettings(defaultConfig))
const healthOk = ref(false)
const healthText = ref('后端未连接')
const validationMessage = ref('')
const validationType = ref('success')
const runId = ref('')
const records = ref([])
const livePeakQueue = ref(0)
const metrics = ref(null)
const currentState = ref(null)
const isRunning = ref(false)
const isDone = ref(false)
const timer = ref(null)
const isRecommending = ref(false)
const recommendation = ref(null)
const explanation = ref(null)
const arrivalMode = ref('manual')
const campusSourceTab = ref('teaching')
const campusLocations = ref({
  cafeterias: [],
  teaching_buildings: [],
  walk_times: {},
  residential_sources: [],
  residential_walk_times: {},
  residential_release_profiles: {},
  population_pool_defaults: {}
})
const selectedCafeteriaId = ref('')
const campusRows = ref([])
const campusSourceMode = ref('manual')
const campusLoadingSource = ref('')
const campusWarning = ref('')
const campusResidentialDetailPanels = ref([])
const campusPopulationPoolForm = reactive({
  total_population_pool: DEFAULT_POPULATION_POOL_BY_PERIOD.lunch.total_population_pool,
  meal_participation_percent: Math.round(DEFAULT_POPULATION_POOL_BY_PERIOD.lunch.meal_participation_rate * 100),
  other_known_population: DEFAULT_POPULATION_POOL_BY_PERIOD.lunch.other_known_population
})
const campusResidentialProfileForm = reactive({
  residential_participation_percent: Math.round(DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch.residential_participation_rate * 100),
  start_time: formatClockMinute(DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch.start_minute),
  end_time: formatClockMinute(DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch.end_minute),
  peak_time: formatClockMinute(DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch.peak_minute),
  distribution: DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch.distribution
})
const residentialCapacityWeights = reactive({})
const residentialPopulationOverrides = reactive({})
const residentialChoicePercents = reactive({})
const campusArrivalRecords = ref([])
const selectedCampusArrivalRecords = ref([])
const campusRecordLoading = ref(false)
const campusRecordSaving = ref(false)
const campusRecordImporting = ref(false)

// ECharts 容器和实例：records 或 metrics 变化后会触发图表刷新。
const queueChartEl = ref(null)
const trendChartEl = ref(null)
const analysisChartEl = ref(null)
let queueChart
let trendChart
let analysisChart
let chartRenderFrame = 0
let chartRenderTimer = 0
let chartRenderScheduledAt = 0
let stepInFlight = false
let awaitingLiveMapTransition = false

// 当前仿真分钟来自最新 StepRecord，尚未运行时为 0。
const currentMinute = computed(() => currentRecord.value?.t ?? 0)
// 最新一条分钟记录，驱动实时指标和地图状态。
const currentRecord = computed(() => records.value.at(-1) || null)
const currentClockMinute = computed(() => clockMinuteFromRecord(currentRecord.value, config.simulation_start_minute))
const currentClockLabel = computed(() => formatClockMinute(currentClockMinute.value))
// 图表只保留最近一段记录，避免实时运行时曲线过长。
const chartRecords = computed(() => records.value.slice(-LIVE_CHART_RECORD_LIMIT))
// 将候选设置转换为窗口、座位、错峰和高峰批次数数组。
const recommendationCandidates = computed(() => buildCandidatesFromSettings(candidateSettings))
// 推荐接口枚举的窗口数量候选。
const windowCandidates = computed(() => recommendationCandidates.value.windows)
// 推荐接口枚举的座位候选，并受当前布局可容纳座位上限约束。
const seatCandidates = computed(() => {
  const seats = recommendationCandidates.value.seats.filter((value) => value <= layoutSeatLimit.value)
  return seats.length ? seats : [config.num_seats]
})
// 推荐接口枚举的错峰分钟候选，空列表时保留 0 分钟兜底。
const staggerCandidates = computed(() => recommendationCandidates.value.staggers.length ? recommendationCandidates.value.staggers : [0])
// 校园模式下推荐接口枚举的下课高峰批次数候选。
const peakCountCandidates = computed(() => recommendationCandidates.value.peakCounts.length ? recommendationCandidates.value.peakCounts : [1])
const layoutSeatLimit = ref(calculateLayoutSeatLimit(layout.value))
const movementMetricsForCards = computed(() => (
  metrics.value
  || currentState.value?.movement_metrics
  || currentRecord.value?.snapshot?.movement_metrics
  || {}
))
const showMovementDetailCards = computed(() => (
  config.movement_quality_preset === 'quality'
  || (!config.movement_quality_preset && config.movement_model === 'advanced_floor_field')
))
// 运行页四张指标卡，实时运行时用最新记录，结束后用最终 metrics。
const runCards = computed(() => {
  const record = currentRecord.value
  const queue = record ? totalQueue(record) : 0
  const peakQueue = metrics.value?.peak_queue ?? livePeakQueue.value
  const physicalEmptySeats = record?.empty_seats ?? currentState.value?.empty_seats ?? config.num_seats
  const reservedSeats = record?.reserved_seats ?? currentState.value?.reserved_seats ?? 0
  const availableSeats = record?.available_seats ?? currentState.value?.available_seats ?? physicalEmptySeats
  const entryWaiting = record?.snapshot?.entry_waiting_count ?? currentState.value?.entry_waiting_count ?? 0
  const movement = movementMetricsForCards.value
  const baseRunCards = [
    { label: '平均等待时间', value: metrics.value ? formatMinutes(metrics.value.avg_wait) : formatMinutes(record?.avg_wait_so_far || 0), hint: metrics.value?.bottleneck_type || '运行中' },
    { label: '当前排队人数', value: queue, hint: `峰值 ${peakQueue} 人 / 边界待入 ${entryWaiting} 人` },
    { label: '物理空座', value: physicalEmptySeats, hint: `当前等座 ${record?.waiting_for_seat_count || 0} 人` },
    { label: '累计接待人数', value: record?.total_seated ?? metrics.value?.throughput ?? 0, hint: `到达 ${record?.total_arrived || 0} 人` }
  ]
  const movementDetailCards = [
    { label: '平均步行时间', value: formatSeconds(movement.avg_walking_time || 0), hint: `可用 ${availableSeats} / 预留 ${reservedSeats}` },
    { label: '路径绕行比', value: formatNumber(movement.avg_walking_distance_ratio || 0), hint: '按目标段统计：实际步行距离 / 直线距离' },
    { label: '移动冲突次数', value: movement.movement_conflict_count ?? 0, hint: '同 tick 目标格冲突' },
    { label: '平均停滞 tick', value: formatNumber(movement.avg_stuck_ticks || 0), hint: '无法移动或等待的 tick' },
    { label: '最大局部密度', value: movement.max_density ?? 0, hint: '邻域内最高人数' }
  ]
  return [
    ...baseRunCards,
    ...(showMovementDetailCards.value ? movementDetailCards : [])
  ]
})
// 分析页指标卡，展示最终等待、排队、利用率、同行行为和座位碎片化。
const analysisCards = computed(() => {
  const m = metrics.value
  const partySplitCount = m?.party_window_split_count ?? m?.party_split_count ?? 0
  const baseAnalysisCards = [
    { label: '平均等待', value: formatMinutes(m?.avg_wait || 0), hint: `取餐排队等待 ${formatMinutes(m?.avg_queue_wait || 0)}` },
    { label: '峰值排队', value: m?.peak_queue ?? 0, hint: `高峰最多等座 ${m?.peak_waiting_for_seat || 0} 人` },
    { label: '全程窗口利用率', value: formatPercent(m?.window_utilization || 0), hint: `服务忙碌期 ${formatPercent(m?.active_window_utilization || 0)} / 瓶颈判断：${m?.bottleneck_type || '待分析'}` },
    { label: '平均座位利用率', value: formatPercent(m?.seat_utilization || 0), hint: `完成就餐 ${m?.total_left || 0} 人 / 已入座 ${m?.throughput || 0} 人` },
    { label: '同行分流次数', value: partySplitCount, hint: '小队成员分配到多个窗口' },
    { label: '同行集合等待', value: formatMinutes(m?.avg_party_gather_wait || 0), hint: `等座排队等待 ${formatMinutes(m?.avg_party_seat_wait || 0)}` },
    { label: '等座小队数', value: m?.blocked_party_count ?? 0, hint: `实际拼桌 ${m?.shared_table_count || 0} 次` },
    { label: '座位碎片化', value: m?.fragmented_seats ?? 0, hint: '空座分散但不适合同桌小队' }
  ]
  const analysisMovementDetailCards = [
    { label: '平均步行时间', value: formatSeconds(m?.avg_walking_time || 0), hint: `入座完成耗时 ${formatMinutes(m?.avg_post_service_to_seat_time || 0)}` },
    { label: '路径绕行比', value: formatNumber(m?.avg_walking_distance_ratio || 0), hint: '按目标段统计：实际步行距离 / 直线距离' },
    { label: '移动冲突次数', value: m?.movement_conflict_count ?? 0, hint: '并行 CA 冲突解决次数' },
    { label: '平均停滞 tick', value: formatNumber(m?.avg_stuck_ticks || 0), hint: '移动等待强度' },
    { label: '最大局部密度', value: m?.max_density ?? 0, hint: '拥堵热力峰值' }
  ]
  return [
    ...baseAnalysisCards,
    ...(showMovementDetailCards.value ? analysisMovementDetailCards : [])
  ]
})
// 运行记录表格倒序展示最近 80 条。
const recentRecords = computed(() => records.value.slice(-80).reverse())
// 校园位置接口返回的食堂列表。
const campusCafeterias = computed(() => campusLocations.value.cafeterias || [])
// 当前校园人数来源的页面展示文本。
const campusSourceLabel = computed(() => {
  if (campusSourceMode.value === 'live') return '实时数据'
  if (campusSourceMode.value === 'random') return '随机生成'
  return '手动填写'
})
const currentMealPeriod = computed(() => config.meal_period || 'lunch')
const campusPopulationPoolPayload = computed(() => {
  return {
    enabled: true,
    meal_period: currentMealPeriod.value,
    total_population_pool: Math.max(0, Math.round(Number(campusPopulationPoolForm.total_population_pool) || 0)),
    total_population_mode: 'manual',
    meal_participation_rate: releasePercentToRatio(campusPopulationPoolForm.meal_participation_percent),
    other_known_population: Math.max(0, Math.round(Number(campusPopulationPoolForm.other_known_population) || 0)),
    residential_allocation_mode: 'capacity_weight',
    residual_policy: 'clamp_zero'
  }
})
const campusResidentialReleaseProfilePayload = computed(() => ({
  meal_period: currentMealPeriod.value,
  start_minute: parseClockTime(campusResidentialProfileForm.start_time),
  end_minute: parseClockTime(campusResidentialProfileForm.end_time),
  peak_minute: parseClockTime(campusResidentialProfileForm.peak_time),
  distribution: campusResidentialProfileForm.distribution || 'triangular',
  residential_participation_rate: releasePercentToRatio(campusResidentialProfileForm.residential_participation_percent)
}))
const currentResidentialReleaseProfile = computed(() => campusResidentialReleaseProfilePayload.value)
const residentialParticipationRate = computed(() => (
  clampRatio(currentResidentialReleaseProfile.value.residential_participation_rate ?? 1)
))
const teachingPopulationEstimate = computed(() => (
  campusRows.value.reduce((sum, row) => (
    sum + (row.floors || []).reduce((floorSum, floor) => (
      floorSum + campusReleasedFloorCount(row, floor)
    ), 0)
  ), 0)
))
const effectiveMealPopulation = computed(() => (
  Math.round(campusPopulationPoolPayload.value.total_population_pool * campusPopulationPoolPayload.value.meal_participation_rate)
))
const residentialResidualPopulation = computed(() => (
  Math.max(
    0,
    effectiveMealPopulation.value
      - teachingPopulationEstimate.value
      - campusPopulationPoolPayload.value.other_known_population
  )
))
const residentialPopulationEstimate = computed(() => (
  Math.round(residentialResidualPopulation.value * residentialParticipationRate.value)
))
const editableResidentialSources = computed(() => (
  (campusLocations.value.residential_sources || []).filter((source) => (
    source.id !== 'main_dorms'
    && source.id !== 'east_dorms'
    && !source.exclude_from_simulation
  )).map((source) => ({
    ...source,
    capacity_weight: residentialCapacityWeight(source.id)
  }))
))
const residentialAllocatedPopulation = computed(() => (
  allocateResidentialPopulationByWeight(residentialPopulationEstimate.value, editableResidentialSources.value)
))
const campusResidentialTableRows = computed(() => (
  editableResidentialSources.value.map((source) => {
    const population = residentialSourcePopulation(source.id)
    return {
      source_id: source.id,
      source_name: source.name,
      source_type: '宿舍',
      campus_area: source.campus_area || '未分类',
      population,
      population_label: `${formatNumber(population)} 人`,
      release_mode: '时间窗口',
      release_window: residentialReleaseWindowLabel(),
      walk_minutes_label: `${residentialWalkMinutes(source.id)} min`,
      basis: residentialPopulationOverrides[source.id] == null ? 'residual 按 source 权重' : '推荐人口覆盖'
    }
  })
))
const campusResidentialAreaSummaryRows = computed(() => {
  const areaMap = new Map()
  campusResidentialTableRows.value.forEach((row) => {
    const areaKey = row.campus_area || '未分类'
    const current = areaMap.get(areaKey) || {
      campus_area: areaKey,
      source_names: [],
      source_count: 0,
      capacity_weight: 0,
      population: 0,
      arrival_population: 0,
      release_window: residentialReleaseWindowLabel(),
      participation_label: formatPercent(residentialParticipationRate.value)
    }
    current.source_names.push(row.source_name)
    current.source_count += 1
    current.capacity_weight += residentialCapacityWeight(row.source_id)
    current.population += row.population
    current.arrival_population += campusTableArrivalPopulation(row)
    areaMap.set(areaKey, current)
  })
  return [...areaMap.values()].map((row) => ({
    ...row,
    source_names: row.source_names.join('、'),
    population_label: `${formatNumber(row.population)} 人`,
    arrival_population_label: `${formatNumber(row.arrival_population)} 人`
  }))
})
const campusResidentialDemandPayload = computed(() => (
  editableResidentialSources.value.map((source) => ({
    residential_id: source.id,
    release_ratio: 1,
    choice_probability: residentialChoiceProbability(source.id),
    population_override: residentialSourcePopulation(source.id),
    source_type: 'residential'
  }))
))

onMounted(() => {
  checkHealth()
  loadCampusLocations()
  loadCampusArrivalRecords()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  pauseRun()
  window.removeEventListener('resize', resizeCharts)
  if (chartRenderFrame) {
    window.cancelAnimationFrame(chartRenderFrame)
  }
  if (chartRenderTimer) {
    window.clearTimeout(chartRenderTimer)
  }
  queueChart?.dispose()
  trendChart?.dispose()
  analysisChart?.dispose()
})

watch(metrics, renderCharts)
watch(activeView, renderCharts)

// 布局编辑器和基础参数需要双向同步：展示时可说明窗口/餐桌拖拽后，
// 最终仍会转成同一份 layout payload 发送给后端。
watch(
  () => config.num_windows,
  (newCount) => {
    if (isSyncingLayout.value) return
    if (!Number.isFinite(newCount) || newCount < 1) return
    if (layout.value.windows.length === newCount) return
    onLayoutUpdate(adjustLayoutWindowCount(layout.value, newCount))
  }
)

watch(
  () => config.num_seats,
  (newCount) => {
    if (isSyncingLayout.value) return
    if (!Number.isFinite(newCount) || newCount < 2) return
    const safeCount = normalizeSeatCount(newCount, layoutSeatLimit.value)
    if (safeCount !== newCount) {
      isSyncingLayout.value = true
      config.num_seats = safeCount
      nextTick(() => { isSyncingLayout.value = false })
      return
    }
    if (totalLayoutSeats(layout.value) === safeCount) return
    onLayoutUpdate(rebuildLayoutTablesForSeats(layout.value, safeCount))
  }
)

// 连通性验证只调用 /api/health，用于确认 Vite proxy 后面的 FastAPI 是否可达。
async function checkHealth() {
  try {
    const res = await api.health()
    healthOk.value = true
    healthText.value = res.message || 'backend ready'
  } catch {
    healthOk.value = false
    healthText.value = '后端未连接'
  }
}

async function loadCampusLocations() {
  try {
    const payload = await api.campusLocations()
    campusLocations.value = payload
    syncCampusPopulationDefaults(config.meal_period || 'lunch')
    seedResidentialCapacityWeights(payload.residential_sources || [])
    // 默认选中第一个食堂，让校园人数模式打开后可以立即计算选择概率。
    if (!selectedCafeteriaId.value && payload.cafeterias?.length) {
      selectedCafeteriaId.value = payload.cafeterias[0].id
    }
    // 如果用户还没填楼层人数，用教学楼元数据先生成空表格。
    if (!campusRows.value.length) {
      campusRows.value = buildEmptyCampusRows(payload.teaching_buildings || [])
    }
  } catch {
    campusWarning.value = '校园位置数据加载失败。'
  }
}

// 根据教学楼基础数据生成可手动填写的楼层人数行。
function defaultCampusDismissalMinute() {
  return Math.max(0, Math.round(Number(config.simulation_start_minute) || 0)) + 30
}

function applyMealPeriodDefaults() {
  const previousDefault = defaultCampusDismissalMinute()
  config.simulation_start_minute = MEAL_START_MINUTES[config.meal_period] ?? MEAL_START_MINUTES.lunch
  syncCampusPopulationDefaults(config.meal_period || 'lunch')
  const nextDefault = defaultCampusDismissalMinute()
  campusRows.value = campusRows.value.map((row) => {
    const currentMinuteValue = Math.max(0, Math.round(Number(row.dismissal_minute) || 0))
    if (row.dismissal_time && currentMinuteValue !== previousDefault) {
      return row
    }
    return {
      ...row,
      dismissal_minute: nextDefault,
      dismissal_time: formatClockMinute(nextDefault)
    }
  })
}

function syncCampusPopulationDefaults(mealPeriod) {
  clearResidentialPopulationOverrides()
  const pool = campusLocations.value.population_pool_defaults?.[mealPeriod]
    || DEFAULT_POPULATION_POOL_BY_PERIOD[mealPeriod]
    || DEFAULT_POPULATION_POOL_BY_PERIOD.lunch
  const profile = campusLocations.value.residential_release_profiles?.[mealPeriod]
    || DEFAULT_RESIDENTIAL_RELEASE_PROFILES[mealPeriod]
    || DEFAULT_RESIDENTIAL_RELEASE_PROFILES.lunch
  campusPopulationPoolForm.total_population_pool = Math.max(0, Math.round(Number(pool.total_population_pool) || 0))
  campusPopulationPoolForm.meal_participation_percent = Math.round(clampRatio(pool.meal_participation_rate ?? 1) * 100)
  campusPopulationPoolForm.other_known_population = Math.max(0, Math.round(Number(pool.other_known_population) || 0))
  campusResidentialProfileForm.residential_participation_percent = Math.round(clampRatio(profile.residential_participation_rate ?? 1) * 100)
  campusResidentialProfileForm.start_time = formatClockMinute(profile.start_minute)
  campusResidentialProfileForm.end_time = formatClockMinute(profile.end_minute)
  campusResidentialProfileForm.peak_time = formatClockMinute(profile.peak_minute ?? Math.round((profile.start_minute + profile.end_minute) / 2))
  campusResidentialProfileForm.distribution = profile.distribution || 'triangular'
}

function applyCampusPopulationPoolConfig(pool) {
  if (!pool) return
  campusPopulationPoolForm.total_population_pool = Math.max(0, Math.round(Number(pool.total_population_pool) || 0))
  campusPopulationPoolForm.meal_participation_percent = Math.round(clampRatio(pool.meal_participation_rate ?? 1) * 100)
  campusPopulationPoolForm.other_known_population = Math.max(0, Math.round(Number(pool.other_known_population) || 0))
}

function applyCampusResidentialProfileConfig(profile) {
  if (!profile) return
  campusResidentialProfileForm.residential_participation_percent = Math.round(clampRatio(profile.residential_participation_rate ?? 1) * 100)
  campusResidentialProfileForm.start_time = formatClockMinute(profile.start_minute)
  campusResidentialProfileForm.end_time = formatClockMinute(profile.end_minute)
  campusResidentialProfileForm.peak_time = formatClockMinute(profile.peak_minute ?? Math.round((Number(profile.start_minute) + Number(profile.end_minute)) / 2))
  campusResidentialProfileForm.distribution = profile.distribution || 'triangular'
}

function applyCampusResidentialSourcesConfig(sources) {
  clearResidentialPopulationOverrides()
  clearResidentialChoiceOverrides()
  for (const source of sources || []) {
    if (!source?.residential_id) continue
    if (source.population_override != null) {
      residentialPopulationOverrides[source.residential_id] = Math.max(0, Math.round(Number(source.population_override) || 0))
    }
    if (source.choice_probability != null) {
      residentialChoicePercents[source.residential_id] = choicePercentFromProbability(source.choice_probability)
    }
  }
}

function clearResidentialPopulationOverrides() {
  Object.keys(residentialPopulationOverrides).forEach((key) => {
    delete residentialPopulationOverrides[key]
  })
}

function clearResidentialChoiceOverrides() {
  Object.keys(residentialChoicePercents).forEach((key) => {
    delete residentialChoicePercents[key]
  })
}

function seedResidentialCapacityWeights(sources) {
  for (const source of sources || []) {
    if (!source?.id || source.id === 'main_dorms' || source.id === 'east_dorms') continue
    if (residentialCapacityWeights[source.id] == null) {
      residentialCapacityWeights[source.id] = Math.max(0, Number(source.capacity_weight) || 0)
    }
  }
}

function syncDismissalTime(row) {
  const dismissalMinute = parseClockTime(row.dismissal_time)
  row.dismissal_minute = dismissalMinute
  row.dismissal_time = formatClockMinute(dismissalMinute)
}

function buildEmptyCampusRows(buildings) {
  const dismissalMinute = defaultCampusDismissalMinute()
  return buildings.map((building) => ({
    building_id: building.id,
    building_name: building.name,
    dismissal_minute: dismissalMinute,
    dismissal_time: formatClockMinute(dismissalMinute),
    release_percent: 100,
    choice_percent: null,
    source: 'manual',
    floors: Array.from({ length: Math.max(1, Number(building.default_floor_count || 5)) }, (_, index) => ({
      floor: index + 1,
      count: 0,
      capacity: 0
    }))
  }))
}

async function loadCampusOccupancy(sourceMode) {
  if (campusLoadingSource.value) return
  try {
    campusLoadingSource.value = sourceMode
    campusWarning.value = ''
    // 已有表格时只请求当前表格中的教学楼；空表格时请求全部教学楼。
    const buildings = campusRows.value.length
      ? campusRows.value.map((row) => row.building_id)
      : (campusLocations.value.teaching_buildings || []).map((item) => item.id)
    const payload = await api.campusOccupancy({
      source_mode: sourceMode,
      buildings,
      seed: config.seed
    })
    applyCampusOccupancyItems(payload.items || [], sourceMode)
    campusSourceMode.value = sourceMode
    campusWarning.value = (payload.warnings || []).join(' ')
    arrivalMode.value = 'campus'
    await saveCampusArrivalRecord({ silent: true, sourceMode })
    ElMessage.success(sourceMode === 'live' ? '已获取校园实时人数' : '已随机生成校园人数')
  } catch (error) {
    campusWarning.value = error?.response?.data?.detail || '校园人数加载失败'
  } finally {
    if (campusLoadingSource.value === sourceMode) {
      campusLoadingSource.value = ''
    }
  }
}

async function loadCampusArrivalRecords() {
  try {
    campusRecordLoading.value = true
    campusArrivalRecords.value = await api.campusArrivalRecords()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '校园到达记录加载失败')
  } finally {
    campusRecordLoading.value = false
  }
}

async function saveCampusArrivalRecord(options = {}) {
  const { silent = false, sourceMode = campusSourceMode.value } = options
  try {
    campusRecordSaving.value = true
    const demand = buildCampusDemandPayload()
    if (!demand?.enabled) {
      if (!silent) ElMessage.warning('请先切换到校园人数模式再保存记录')
      return null
    }
    const record = await api.saveCampusArrivalRecord({
      campus_demand: {
        ...demand,
        source_mode: sourceMode || demand.source_mode
      }
    })
    upsertCampusArrivalRecord(record)
    if (!silent) ElMessage.success('已保存校园到达记录')
    return record
  } catch (error) {
    if (!silent) {
      ElMessage.error(error?.response?.data?.detail || '校园到达记录保存失败')
    }
    return null
  } finally {
    campusRecordSaving.value = false
  }
}

function upsertCampusArrivalRecord(record) {
  if (!record?.record_id) return
  campusArrivalRecords.value = [
    record,
    ...campusArrivalRecords.value.filter((item) => item.record_id !== record.record_id)
  ]
}

function onCampusRecordSelectionChange(selection) {
  selectedCampusArrivalRecords.value = selection
}

function importCampusArrivalRecord(row) {
  if (!row?.campus_demand) return
  applyCampusDemandConfig(row.campus_demand)
  activeView.value = 'config'
  ElMessage.success('已导入校园到达记录')
}

async function importSelectedCampusArrivalAverage() {
  const selected = selectedCampusArrivalRecords.value
  if (!selected.length) return
  if (selected.length === 1) {
    importCampusArrivalRecord(selected[0])
    return
  }
  try {
    campusRecordImporting.value = true
    const average = await api.campusArrivalRecordAverage({
      record_ids: selected.map((record) => record.record_id)
    })
    applyCampusDemandConfig(average.campus_demand)
    activeView.value = 'config'
    ElMessage.success(`已导入 ${selected.length} 条校园到达记录的平均值`)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '导入平均记录失败')
  } finally {
    campusRecordImporting.value = false
  }
}

// 将实时/随机人数接口返回的楼层人数写回页面表格。
function applyCampusOccupancyItems(items, sourceMode) {
  const byId = new Map(items.map((item) => [item.building_id, item]))
  // 接口返回可能只覆盖部分楼宇，baseRows 保留用户已经编辑过的行。
  const baseRows = campusRows.value.length
    ? campusRows.value
    : items.map((item) => ({
      building_id: item.building_id,
      building_name: item.building_name,
      dismissal_minute: defaultCampusDismissalMinute(),
      dismissal_time: formatClockMinute(defaultCampusDismissalMinute()),
      release_percent: 100,
      choice_percent: null,
      source: sourceMode,
      floors: []
    }))
  campusRows.value = baseRows.map((row) => {
    const item = byId.get(row.building_id)
    if (!item) return row
    const dismissalMinute = Math.max(0, Math.round(Number(row.dismissal_minute ?? defaultCampusDismissalMinute()) || 0))
    const releasePercent = Number.isFinite(Number(row.release_percent))
      ? Number(row.release_percent)
      : releasePercentFromRatio(row.release_ratio ?? 1)
    return {
      ...row,
      // 保留用户设置的就餐比例，只替换人数来源和楼层人数。
      dismissal_minute: dismissalMinute,
      dismissal_time: row.dismissal_time || formatClockMinute(dismissalMinute),
      release_percent: releasePercent,
      choice_percent: row.choice_percent ?? null,
      source: item.source || sourceMode,
      floors: (item.floors || []).map((floor) => ({
        floor: Number(floor.floor) || 1,
        count: Number(floor.count) || 0,
        capacity: Number(floor.capacity) || 0
      }))
    }
  })
}

// 将推荐方案或后端配置中的校园到达参数还原到页面控件。
function applyCampusDemandConfig(campusDemand) {
  if (!campusDemand?.enabled) return
  arrivalMode.value = 'campus'
  selectedCafeteriaId.value = campusDemand.cafeteria_id || selectedCafeteriaId.value
  campusSourceMode.value = campusDemand.source_mode || 'manual'
  applyCampusPopulationPoolConfig(campusDemand.population_pool)
  applyCampusResidentialProfileConfig(campusDemand.residential_release_profile)
  applyCampusResidentialSourcesConfig(campusDemand.residential_sources)
  // 推荐接口返回的是 building_id，页面展示需要补回教学楼名称。
  const buildingNames = new Map(
    (campusLocations.value.teaching_buildings || []).map((building) => [building.id, building.name])
  )
  campusRows.value = (campusDemand.buildings || []).map((building) => ({
    building_id: building.building_id,
    building_name: buildingNames.get(building.building_id) || building.building_id,
    dismissal_minute: Math.max(0, Math.round(Number(building.dismissal_minute) || 0)),
    dismissal_time: formatClockMinute(Math.max(0, Math.round(Number(building.dismissal_minute) || 0))),
    release_percent: releasePercentFromRatio(building.release_ratio ?? 1),
    choice_percent: choicePercentFromProbability(building.choice_probability),
    source: campusSourceMode.value,
    floors: (building.floors || []).map((floor) => ({
      floor: Math.max(1, Math.round(Number(floor.floor) || 1)),
      count: Math.max(0, Math.round(Number(floor.count) || 0)),
      capacity: Number(floor.capacity) || 0
    }))
  }))
}

// 三档仿真质量预设会同步到底层 movement_model 和高级移动参数。
function applyMovementQualityPreset(preset) {
  const settings = movementQualityPresets[preset]
  if (!settings) return
  Object.assign(config, settings)
}

// 恢复页面默认参数、默认布局和推荐候选设置。
function loadDefault() {
  isSyncingLayout.value = true
  Object.assign(config, defaultConfig)
  arrivalMode.value = 'manual'
  campusSourceMode.value = 'manual'
  campusWarning.value = ''
  clearResidentialChoiceOverrides()
  campusRows.value = buildEmptyCampusRows(campusLocations.value.teaching_buildings || [])
  layout.value = createDefaultLayout(defaultConfig)
  layoutSeatLimit.value = calculateLayoutSeatLimit(layout.value)
  resetCandidateSettings()
  validationMessage.value = ''
  nextTick(() => { isSyncingLayout.value = false })
}

// 按当前基础参数重新生成布局，并同步座位数和窗口数。
function resetLayout() {
  isSyncingLayout.value = true
  layout.value = createDefaultLayout(config)
  layoutSeatLimit.value = calculateLayoutSeatLimit(layout.value)
  config.num_seats = totalLayoutSeats(layout.value)
  config.num_windows = layout.value.windows.length
  ElMessage.info('已根据当前参数重置布局')
  nextTick(() => { isSyncingLayout.value = false })
}

// 基于当前资源数量生成更适合室内蛇形队列和服务通道的布局。
function optimizeCurrentLayout() {
  isSyncingLayout.value = true
  const optimized = optimizeLayoutForFlow(layout.value, config)
  layout.value = optimized
  layoutSeatLimit.value = calculateLayoutSeatLimit(optimized)
  config.num_seats = totalLayoutSeats(optimized)
  config.num_windows = optimized.windows.length
  if (optimized.floor) {
    config.floor_width = optimized.floor.width
    config.floor_height = optimized.floor.height
  }
  ElMessage.success('已优化布局：保留窗口和座位规模，扩大室内排队通道')
  nextTick(() => { isSyncingLayout.value = false })
}

// 清洗窗口数量输入，具体布局增减由 watch/布局编辑器同步。
function updateWindowCount(value) {
  config.num_windows = Math.min(30, Math.max(1, Math.round(Number(value) || 1)))
}

// 清洗座位数量输入，并限制在当前布局可容纳上限内。
function updateSeatCount(value) {
  config.num_seats = normalizeSeatCount(value, layoutSeatLimit.value)
}

// 接收布局编辑器更新，同步布局、座位数、窗口数和地面尺寸配置。
function onLayoutUpdate(nextLayout, meta = {}) {
  // 拖拽过程中 meta.transient=true 时不反复重算座位上限，减少编辑卡顿。
  const shouldRefreshSeatLimit = Boolean(meta?.forceSeatLimit) || (
    !meta?.transient && layoutCapacitySignature(layout.value) !== layoutCapacitySignature(nextLayout)
  )
  const limit = shouldRefreshSeatLimit ? calculateLayoutSeatLimit(nextLayout) : layoutSeatLimit.value
  if (shouldRefreshSeatLimit) {
    layoutSeatLimit.value = limit
  }
  // 当前布局座位超过可容纳上限时，按上限重建餐桌，避免提交无法摆放的座位数。
  const boundedLayout = totalLayoutSeats(nextLayout) > limit
    ? rebuildLayoutTablesForSeats(nextLayout, limit)
    : nextLayout
  layout.value = boundedLayout
  const total = totalLayoutSeats(boundedLayout)
  if (config.num_seats !== total) {
    // isSyncingLayout 防止 config watcher 再次反向重建布局。
    isSyncingLayout.value = true
    config.num_seats = total
    nextTick(() => { isSyncingLayout.value = false })
  }
  if (config.num_windows !== boundedLayout.windows.length) {
    // 窗口数量同样以布局编辑器实际对象数为准。
    isSyncingLayout.value = true
    config.num_windows = boundedLayout.windows.length
    nextTick(() => { isSyncingLayout.value = false })
  }
  if (boundedLayout.floor) {
    config.floor_width = boundedLayout.floor.width
    config.floor_height = boundedLayout.floor.height
  }
}

// 用影响可容纳座位数的地面、门、窗口字段生成轻量签名。
function layoutCapacitySignature(targetLayout) {
  const floor = targetLayout?.floor || {}
  const doors = (targetLayout?.doors || []).map((item) => `${item.id}:${item.x}:${item.y}:${item.wall_side}`).join('|')
  const windows = (targetLayout?.windows || []).map((item) => `${item.id}:${item.x}:${item.y}:${item.wall_side}`).join('|')
  return `${floor.x}:${floor.y}:${floor.width}:${floor.height}::${doors}::${windows}`
}

// 根据当前基础配置重置推荐候选范围。
function resetCandidateSettings() {
  Object.assign(candidateSettings, createDefaultCandidateSettings(config))
}

// 参数校验会把当前表单和布局整理成后端请求体，再交给 FastAPI/Pydantic 校验。
async function validateConfig() {
  refreshCampusDemandConfig()
  const result = await api.validateConfig(buildSimulationConfigPayload(config, layout.value))
  validationType.value = result.valid ? (result.warnings.length ? 'warning' : 'success') : 'error'
  validationMessage.value = result.valid
    ? result.warnings[0] || '参数校验通过。'
    : result.errors.join(' ')
  return result.valid
}

// 点击“开始仿真”的入口：第一次运行会 reset 并请求首个单步，
// 后续自动运行则由定时器持续调用 singleStep(false)。
async function startLiveRun() {
  if (isRunning.value) return
  isRunning.value = true
  activeView.value = 'run'
  if (!runId.value || isDone.value) {
    // 新一轮运行必须清空旧 run_id 和旧记录，再用 reset=true 创建后端 runner。
    resetRun(false)
    isRunning.value = true
    activeView.value = 'run'
    const response = await singleStep(true, { waitForMapTransition: true })
    if (!response) {
      awaitingLiveMapTransition = false
      return
    }
    if (isDone.value) return
    return
  }
  if (isDone.value) return
  // 已有未结束 run_id 时直接续跑，不重新提交完整配置。
  scheduleNextLiveStep()
}

// 停止实时自动步进并清理定时器。
function pauseRun() {
  isRunning.value = false
  if (timer.value) {
    window.clearTimeout(timer.value)
    timer.value = null
  }
}

// 在地图动画结束或固定延迟后安排下一次实时单步请求。
function scheduleNextLiveStep(delayMs = liveStepDelay(LIVE_TRANSITION_MS)) {
  if (typeof window === 'undefined' || !isRunning.value || isDone.value) return
  if (timer.value) {
    window.clearTimeout(timer.value)
  }
  timer.value = window.setTimeout(runScheduledLiveStep, delayMs)
}

async function runScheduledLiveStep() {
  timer.value = null
  if (!shouldRequestLiveStep({ isRunning: isRunning.value, isDone: isDone.value, stepInFlight })) {
    return
  }
  const response = await singleStep(false, { waitForMapTransition: true })
  if (!response) {
    awaitingLiveMapTransition = false
  }
}

// 地图动画播放完后再调度下一次 step，保证视觉状态不跳帧。
function onLiveMapTransitionSettled() {
  if (!awaitingLiveMapTransition) return
  awaitingLiveMapTransition = false
  if (isRunning.value && !isDone.value) {
    scheduleNextLiveStep(liveStepDelay(0))
  }
}

// 清空当前运行的 run_id、记录、指标和地图状态。
function resetRun(clearMessage = true) {
  pauseRun()
  awaitingLiveMapTransition = false
  runId.value = ''
  records.value = []
  livePeakQueue.value = 0
  metrics.value = null
  currentState.value = null
  isDone.value = false
  recommendation.value = null
  explanation.value = null
  if (clearMessage) ElMessage.info('仿真已重置')
  renderCharts()
}

// 后端每返回一条 StepRecord，就追加到 records；指标卡片和趋势图都从这里取数据。
// appendRunRecord() 追加后端返回的分钟记录并触发图表刷新。
function appendRunRecord(record) {
  if (!record) return
  records.value.push(record)
  const overflow = records.value.length - LIVE_RECORD_LIMIT
  if (overflow > 0) {
    records.value.splice(0, overflow)
  }
  livePeakQueue.value = Math.max(livePeakQueue.value, totalQueue(record))
  renderChartsThrottled()
}

// 实时仿真的核心前端请求：reset=true 时携带完整 config 新建 runner，
// reset=false 时只携带 run_id，让后端继续推进同一个 DiningSimulationRunner。
async function singleStep(reset = false, options = {}) {
  if (stepInFlight) return null
  stepInFlight = true
  try {
    refreshCampusDemandConfig()
    // reset=true 首步提交完整配置；普通步进只发 run_id，保持后端内存状态连续。
    const payload = shouldResetStepRun(reset, runId.value)
      ? { config: buildSimulationConfigPayload(config, layout.value), reset: true }
      : { run_id: runId.value }
    const response = await api.stepSimulation(payload)
    runId.value = response.run_id
    appendRunRecord(response.record)
    if (options?.waitForMapTransition) {
      // 让下一次请求等待地图动画 settled 事件，避免学生位置突然跳到下一分钟。
      awaitingLiveMapTransition = true
    }
    currentState.value = response.state
    isDone.value = response.done
    if (response.metrics) {
      // 后端只在 done=true 时返回 metrics，此时切到分析页并停止自动步进。
      metrics.value = response.metrics
      pauseRun()
      activeView.value = 'analysis'
    }
    return response
  } catch (error) {
    pauseRun()
    ElMessage.error(error?.response?.data?.detail || '单步运行失败')
    return null
  } finally {
    stepInFlight = false
  }
}

async function runFullSimulation() {
  try {
    pauseRun()
    refreshCampusDemandConfig()
    const response = await api.runSimulation(buildSimulationConfigPayload(config, layout.value))
    applyRunResponse(response)
    activeView.value = 'analysis'
    ElMessage.success('仿真运行完成')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '完整仿真失败')
  }
}

// 将完整仿真响应写入页面状态，并刷新图表。
function applyRunResponse(response) {
  runId.value = response.run_id
  // 完整仿真可能记录很多分钟，前端只保留最近一段用于表格和图表。
  records.value = (response.records || []).slice(-LIVE_RECORD_LIMIT)
  metrics.value = response.metrics
  // 如果 metrics 不存在，则用记录临时计算峰值排队，兼容异常响应。
  livePeakQueue.value = response.metrics?.peak_queue ?? records.value.reduce((peak, record) => Math.max(peak, totalQueue(record)), 0)
  currentState.value = response.final_state
  isDone.value = true
  renderCharts()
}

// 优化推荐链路：前端只提交基准配置和候选范围，后端负责枚举、评分和规则化解释。
async function generateRecommendation() {
  try {
    isRecommending.value = true
    refreshCampusDemandConfig()
    // 候选范围在前端生成数组，后端只负责对这些明确候选评分排序。
    const payload = {
      base_config: buildSimulationConfigPayload(config, layout.value),
      window_options: windowCandidates.value,
      seat_options: seatCandidates.value,
      stagger_options: staggerCandidates.value,
      peak_count_options: peakCountCandidates.value,
      top_k: 4
    }
    recommendation.value = await api.recommend(payload)
    // 推荐完成后，把基准/最优指标再送到解释接口生成面向展示的文字说明。
    explanation.value = await api.explain({
      run_id: runId.value || null,
      baseline_config: buildSimulationConfigPayload(config, layout.value),
      best_config: recommendation.value.best.config,
      baseline_metrics: recommendation.value.baseline_metrics,
      best_metrics: recommendation.value.best.metrics,
      root_cause_summary: metrics.value?.bottleneck_type || recommendation.value.baseline_metrics.bottleneck_type,
      recommended_strategy: recommendation.value.best.strategy
    })
    activeView.value = nextViewAfterRecommendation(activeView.value)
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '生成推荐失败')
  } finally {
    isRecommending.value = false
  }
}

// 将页面的校园到达表格同步到 config.campus_demand。
function refreshCampusDemandConfig() {
  config.campus_demand = buildCampusDemandPayload()
}

// 将校园到达页面表格整理为后端 SimulationConfig.campus_demand。
function buildCampusDemandPayload() {
  if (arrivalMode.value !== 'campus') return null
  return {
    enabled: true,
    cafeteria_id: selectedCafeteriaId.value,
    source_mode: campusSourceMode.value,
    meal_period: config.meal_period || 'lunch',
    residential_sources: campusResidentialDemandPayload.value,
    population_pool: campusPopulationPoolPayload.value,
    residential_release_profile: campusResidentialReleaseProfilePayload.value,
    // 页面百分比和输入框中的人数在这里清洗成后端 dataclass 需要的数值。
    buildings: campusRows.value.map((row) => ({
      building_id: row.building_id,
      dismissal_minute: parseClockTime(row.dismissal_time ?? row.dismissal_minute),
      release_ratio: releasePercentToRatio(row.release_percent),
      choice_probability: campusTableChoiceProbability(row),
      floors: (row.floors || []).map((floor) => ({
        floor: Math.max(1, Math.round(Number(floor.floor) || 1)),
        count: Math.max(0, Math.round(Number(floor.count) || 0))
      }))
    }))
  }
}

function campusReleasedPopulation(row) {
  return (row.floors || []).reduce((sum, floor) => sum + campusReleasedFloorCount(row, floor), 0)
}

// 与后端 estimate_teaching_population 保持一致：每层先乘就餐比例再四舍五入。
function campusReleasedFloorCount(row, floor) {
  return Math.max(0, Math.round((Number(floor.count) || 0) * releasePercentToRatio(row.release_percent)))
}

// 读取当前教学楼到选中食堂的步行分钟数。
function campusWalkMinutes(row) {
  const route = campusLocations.value.walk_times?.[row.building_id]?.[selectedCafeteriaId.value]
  return route?.duration_min ?? '-'
}

function residentialWalkMinutes(residentialId) {
  const route = campusLocations.value.residential_walk_times?.[residentialId]?.[selectedCafeteriaId.value]
  return route?.duration_min ?? '-'
}

function residentialReleaseWindowLabel() {
  const profile = currentResidentialReleaseProfile.value
  return `${formatClockMinute(profile.start_minute)}-${formatClockMinute(profile.end_minute)}`
}

function isResidentialCampusRow(row) {
  return row?.source_type === '宿舍'
}

function campusTableWalkMinutes(row) {
  return isResidentialCampusRow(row) ? residentialWalkMinutes(row.source_id) : campusWalkMinutes(row)
}

function campusTablePopulationLabel(row) {
  return `${formatNumber(campusTableArrivalPopulation(row))} 人`
}

function campusTableChoiceProbability(row) {
  return releasePercentToRatio(campusTableChoicePercent(row))
}

function campusTableArrivalPopulation(row) {
  if (isResidentialCampusRow(row)) {
    return Math.round(row.population * campusTableChoiceProbability(row))
  }
  return Math.round(campusReleasedPopulation(row) * campusTableChoiceProbability(row))
}

function residentialCapacityWeight(residentialId) {
  const source = (campusLocations.value.residential_sources || []).find((item) => item.id === residentialId)
  return Math.max(0, Number(residentialCapacityWeights[residentialId] ?? source?.capacity_weight ?? 0) || 0)
}

function updateResidentialCapacityWeight(residentialId, value) {
  residentialCapacityWeights[residentialId] = Math.max(0, Number(value) || 0)
  delete residentialPopulationOverrides[residentialId]
}

function residentialSourcePopulation(residentialId) {
  if (residentialPopulationOverrides[residentialId] != null) {
    return Math.max(0, Math.round(Number(residentialPopulationOverrides[residentialId]) || 0))
  }
  return residentialAllocatedPopulation.value[residentialId] || 0
}

function allocateResidentialPopulationByWeight(population, sources) {
  const totalPopulation = Math.max(0, Math.round(Number(population) || 0))
  const validSources = (sources || []).filter((source) => (
    source.id !== 'main_dorms'
    && source.id !== 'east_dorms'
    && !source.exclude_from_simulation
    && Number(source.capacity_weight) > 0
  ))
  const totalWeight = validSources.reduce((sum, source) => sum + Number(source.capacity_weight), 0)
  if (!totalPopulation || totalWeight <= 0) {
    return Object.fromEntries(validSources.map((source) => [source.id, 0]))
  }

  const allocations = validSources.map((source) => {
    const exact = totalPopulation * Number(source.capacity_weight) / totalWeight
    const base = Math.floor(exact)
    return { id: source.id, base, remainder: exact - base }
  })
  let remaining = totalPopulation - allocations.reduce((sum, item) => sum + item.base, 0)
  allocations
    .slice()
    .sort((a, b) => (b.remainder - a.remainder) || String(a.id).localeCompare(String(b.id)))
    .forEach((item) => {
      if (remaining <= 0) return
      item.base += 1
      remaining -= 1
    })
  return Object.fromEntries(allocations.map((item) => [item.id, item.base]))
}

function clampRatio(value) {
  return Math.min(1, Math.max(0, Number(value) || 0))
}

// 将后端 0-1 释放比例转换为页面百分比输入值。
function releasePercentFromRatio(value) {
  const ratio = clampRatio(value)
  return Math.round(ratio * 100)
}

// 将页面百分比输入值转换为后端 0-1 释放比例。
function releasePercentToRatio(value) {
  const percent = Math.min(100, Math.max(0, Number(value) || 0))
  return percent / 100
}

function choicePercentFromProbability(value) {
  if (value == null) return null
  return releasePercentFromRatio(value)
}

function normalizedPercent(value) {
  return Math.min(100, Math.max(0, Number(value) || 0))
}

function campusTableChoicePercent(row) {
  if (isResidentialCampusRow(row)) {
    return residentialChoicePercent(row.source_id)
  }
  if (row?.choice_percent != null && Number.isFinite(Number(row.choice_percent))) {
    return normalizedPercent(row.choice_percent)
  }
  return releasePercentFromRatio(campusChoiceProbability(row))
}

function updateCampusRowChoicePercent(row, value) {
  row.choice_percent = normalizedPercent(value)
}

function residentialChoicePercent(residentialId) {
  if (residentialChoicePercents[residentialId] != null && Number.isFinite(Number(residentialChoicePercents[residentialId]))) {
    return normalizedPercent(residentialChoicePercents[residentialId])
  }
  return releasePercentFromRatio(estimatedResidentialChoiceProbability(residentialId))
}

function updateResidentialChoicePercent(residentialId, value) {
  residentialChoicePercents[residentialId] = normalizedPercent(value)
}

// 按步行时间估算该教学楼学生选择当前食堂的概率。
function campusChoiceProbability(row) {
  const routes = campusLocations.value.walk_times?.[row.building_id]
  if (!routes || !selectedCafeteriaId.value || !routes[selectedCafeteriaId.value]) return 0
  // duration_s 越短，权重越高；nearest/duration 保证最近食堂权重为 1。
  const durations = Object.fromEntries(
    Object.entries(routes).map(([cafeteriaId, route]) => [cafeteriaId, Math.max(1, Number(route.duration_s) || 1)])
  )
  const nearest = Math.min(...Object.values(durations))
  // 2.4 次方让近距离优势更明显，与后端校园到达概率保持同一口径。
  const weights = Object.fromEntries(
    Object.entries(durations).map(([cafeteriaId, duration]) => [cafeteriaId, Math.pow(nearest / duration, 2.4)])
  )
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0)
  return total > 0 ? weights[selectedCafeteriaId.value] / total : 0
}

function estimatedResidentialChoiceProbability(residentialId) {
  const routes = campusLocations.value.residential_walk_times?.[residentialId]
  if (!routes || !selectedCafeteriaId.value || !routes[selectedCafeteriaId.value]) return 0
  const durations = Object.fromEntries(
    Object.entries(routes).map(([cafeteriaId, route]) => [cafeteriaId, Math.max(1, Number(route.duration_s) || 1)])
  )
  const nearest = Math.min(...Object.values(durations))
  const weights = Object.fromEntries(
    Object.entries(durations).map(([cafeteriaId, duration]) => [cafeteriaId, Math.pow(nearest / duration, 2.4)])
  )
  const total = Object.values(weights).reduce((sum, value) => sum + value, 0)
  return total > 0 ? weights[selectedCafeteriaId.value] / total : 0
}

function residentialChoiceProbability(residentialId) {
  return releasePercentToRatio(residentialChoicePercent(residentialId))
}

// 将推荐方案写回基础参数，并重新生成对应布局。
function applyRecommendationConfig(recommendedConfig) {
  applyRecommendedConfig(config, recommendedConfig)
  if (recommendedConfig.campus_demand) {
    applyCampusDemandConfig(recommendedConfig.campus_demand)
  }
  isSyncingLayout.value = true
  layout.value = createDefaultLayout(config)
  validationMessage.value = ''
  ElMessage.success('已应用方案到基础参数')
  nextTick(() => { isSyncingLayout.value = false })
}

// 打开后端 CSV 导出地址，下载当前 run_id 的分钟记录。
function exportRecords() {
  if (runId.value) {
    window.open(api.exportUrl(runId.value), '_blank')
  }
}

// 限制实时单步期间图表刷新频率，避免连续 step 触发过多重绘。
function renderChartsThrottled() {
  const nowMs = Date.now()
  const elapsed = nowMs - chartRenderScheduledAt
  if (elapsed >= LIVE_CHART_RENDER_INTERVAL_MS) {
    // 间隔已到时立即刷新，并记录本次刷新时刻。
    chartRenderScheduledAt = nowMs
    renderCharts()
    return
  }
  if (chartRenderTimer) return
  // 间隔未到时只挂一个延迟刷新，避免同一分钟内累积多个 timer。
  chartRenderTimer = window.setTimeout(() => {
    chartRenderTimer = 0
    chartRenderScheduledAt = Date.now()
    renderCharts()
  }, LIVE_CHART_RENDER_INTERVAL_MS - elapsed)
}

// 图表刷新使用 requestAnimationFrame，避免实时单步返回太快时频繁重绘。
// renderCharts() 统一调度队列图、趋势图和分析图重绘。
function renderCharts() {
  nextTick(() => {
    if (chartRenderFrame) {
      window.cancelAnimationFrame(chartRenderFrame)
    }
    // 两层 requestAnimationFrame 给 Element Plus 页签切换后的容器尺寸留出布局时间。
    chartRenderFrame = window.requestAnimationFrame(() => {
      chartRenderFrame = window.requestAnimationFrame(() => {
        chartRenderFrame = 0
        renderQueueChart()
        renderTrendChart()
        renderAnalysisChart()
      })
    })
  })
}

// 绘制当前每个窗口的排队人数柱状图。
function renderQueueChart() {
  const element = queueChartEl.value
  if (!canRenderChartElement(element)) return
  queueChart ||= echarts.init(element)
  queueChart.resize()
  const lengths = currentRecord.value?.queue_lengths || Array.from({ length: config.num_windows }, () => 0)
  queueChart.setOption({
    animation: false,
    color: ['#3f6fa9'],
    grid: { left: 34, right: 16, top: 24, bottom: 30 },
    xAxis: { type: 'category', data: lengths.map((_, index) => `W${index + 1}`) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: lengths, barMaxWidth: 44 }]
  })
}

// 绘制运行页小尺寸趋势图。
function renderTrendChart() {
  const element = trendChartEl.value
  if (!canRenderChartElement(element)) return
  trendChart ||= echarts.init(element)
  trendChart.resize()
  trendChart.setOption(trendOption())
}

// 绘制分析页大尺寸趋势图。
function renderAnalysisChart() {
  const element = analysisChartEl.value
  if (!canRenderChartElement(element)) return
  analysisChart ||= echarts.init(element)
  analysisChart.resize()
  analysisChart.setOption(trendOption(true))
}

// 趋势图数据优先使用后端最终 metrics.chart_data；实时运行未结束时，
// 则从最近的 StepRecord 临时拼出队列、空座、吞吐和等座曲线。
// 生成 ECharts 趋势图配置，结束后优先使用后端 chart_data。
function trendOption(large = false) {
  // 完整仿真结束后用后端 chart_data；实时运行中用本地 records 临时拼曲线。
  const chart = metrics.value?.chart_data || {
    times: chartRecords.value.map((item) => item.t),
    queue_totals: chartRecords.value.map((item) => totalQueue(item)),
    empty_seats: chartRecords.value.map((item) => item.empty_seats),
    throughput: chartRecords.value.map((item) => item.total_seated),
    avg_wait: chartRecords.value.map((item) => item.avg_wait_so_far),
    waiting_for_seat: chartRecords.value.map((item) => item.waiting_for_seat_count)
  }
  return {
    animation: false,
    color: ['#2f65a3', '#d9912f', '#579a58', '#a94e4e'],
    tooltip: { trigger: 'axis' },
    legend: large ? { top: 0 } : { show: false },
    grid: { left: 42, right: 18, top: large ? 42 : 24, bottom: 30 },
    xAxis: { type: 'category', data: chart.times || [] },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '队列长度', type: 'line', smooth: true, data: chart.queue_totals || [] },
      { name: '空座位', type: 'line', smooth: true, data: chart.empty_seats || [] },
      { name: '累计接待', type: 'line', smooth: true, data: chart.throughput || [] },
      { name: '等座人数', type: 'line', smooth: true, data: chart.waiting_for_seat || [] }
    ]
  }
}

// 浏览器窗口尺寸变化时同步调整三个 ECharts 实例。
function resizeCharts() {
  queueChart?.resize()
  trendChart?.resize()
  analysisChart?.resize()
}

// 汇总单条 StepRecord 中所有窗口队列长度。
function totalQueue(record) {
  return (record?.queue_lengths || []).reduce((sum, value) => sum + value, 0)
}

// 将分钟数格式化为指标卡展示文本。
function formatMinutes(value) {
  return `${formatNumber(value)} min`
}

// 将秒数格式化为移动指标展示文本。
function formatSeconds(value) {
  return `${formatNumber(value)} s`
}

// 将 0-1 比例格式化为百分比展示文本。
function formatPercent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`
}

function formatCampusRecordTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(date)
}

function campusRecordSourceLabel(value) {
  if (value === 'live') return '实时'
  if (value === 'random') return '随机'
  if (value === 'average') return '平均'
  return '手动'
}

function mealPeriodLabel(value) {
  const labels = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    weekend: '周末'
  }
  return labels[value] || value || '-'
}

function cafeteriaName(cafeteriaId) {
  return campusCafeterias.value.find((item) => item.id === cafeteriaId)?.name || cafeteriaId || '-'
}

// 整数不显示小数，非整数保留一位。
function formatNumber(value) {
  const number = Number(value) || 0
  return number.toFixed(number % 1 === 0 ? 0 : 1)
}

// 将推荐候选配置压缩成“窗口/座位/错峰”的摘要。
function formatConfigSummary(item) {
  return `${item.num_windows} 窗 / ${item.num_seats} 座 / ${formatStagger(item.stagger_minutes)}`
}

// 将错峰分钟数格式化为中文摘要。
function formatStagger(value) {
  const minutes = Number(value) || 0
  return minutes === 0 ? '不启用错峰' : `错峰 ${minutes} 分钟`
}
</script>
