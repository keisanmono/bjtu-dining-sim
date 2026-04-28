export function formatStaggerCandidate(minutes) {
  return minutes === 0 ? '不启用' : `${minutes} 分钟`
}

export function buildCandidateGroups(windowCandidates, seatCandidates, staggerCandidates) {
  return [
    {
      key: 'windows',
      label: '窗口',
      values: windowCandidates.map((value) => `${value} 个`)
    },
    {
      key: 'seats',
      label: '座位',
      values: seatCandidates.map((value) => `${value} 个`)
    },
    {
      key: 'stagger',
      label: '错峰',
      values: staggerCandidates.map(formatStaggerCandidate)
    }
  ]
}
