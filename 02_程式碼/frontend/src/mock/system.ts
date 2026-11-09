import type { Tone } from '../components/ui'

/** 系統層示範資料：背景工作、通知、稽核、備份。 */

export type JobStatus = '執行中' | '完成' | '失敗' | '排隊中' | '已停止'

export const jobStatusTone: Record<JobStatus, Tone> = { 執行中: 'steel', 完成: 'ok', 失敗: 'alert', 排隊中: 'neutral', 已停止: 'neutral' }

export interface Job {
  id: string
  kind: string
  target: string
  status: JobStatus
  started: string
  by: string
  progress?: number
  error?: string
  events: { title: string; time: string; note?: string; tone?: Tone }[]
}

export const jobs: Job[] = [
  {
    id: 'JOB-0142',
    kind: '訓練（示範）',
    target: 'RUN-DEMO-01',
    status: '執行中',
    started: '09:40',
    by: '研究人員',
    progress: 45,
    events: [
      { title: '排入佇列', time: '09:40' },
      { title: '開始訓練', time: '09:40', note: 'CPU，fold 2／5' },
      { title: '完成 epoch 18', time: '10:02', note: 'val weighted kappa 0.58' },
    ],
  },
  {
    id: 'JOB-0141',
    kind: '臨床分析',
    target: 'EX-1023-07',
    status: '執行中',
    started: '09:41',
    by: '接收程序',
    progress: 35,
    events: [
      { title: '排入佇列', time: '09:41' },
      { title: '影像篩選完成', time: '09:42' },
      { title: '分割中', time: '09:42' },
    ],
  },
  { id: 'JOB-0140', kind: '病人層級切分', target: '資料集版本 dsv-001', status: '排隊中', started: '—', by: '研究人員', events: [{ title: '排入佇列', time: '09:38' }] },
  {
    id: 'JOB-0139',
    kind: '報告產出',
    target: 'R-0011',
    status: '完成',
    started: '昨天 16:45',
    by: '林醫師',
    events: [
      { title: '開始產生 PDF', time: '昨天 16:45' },
      { title: '完成', time: '昨天 16:45', tone: 'ok' },
    ],
  },
  {
    id: 'JOB-0138',
    kind: '臨床分析',
    target: 'EX-1023-02',
    status: '失敗',
    started: '今天 07:49',
    by: '接收程序',
    error: 'SEGMENTATION_FAILED：分割模型無法找到腎臟輪廓（2 張影像）',
    events: [
      { title: '排入佇列', time: '07:49' },
      { title: '分割失敗', time: '07:50', note: '2 張影像找不到腎臟輪廓', tone: 'alert' },
    ],
  },
]

export const runningJobCount = jobs.filter((j) => j.status === '執行中').length

export const notifications = [
  { id: 'N-1', text: 'EX-1023-06 分析完成，等待確認分級', time: '09:20', to: '/clinical/exams/EX-1023-06', unread: true },
  { id: 'N-2', text: 'R-0105 已送出，等待簽核', time: '09:05', to: '/clinical/reports', unread: true },
  { id: 'N-3', text: 'EX-1023-02 分析失敗，可重試', time: '07:50', to: '/jobs', unread: true },
  { id: 'N-4', text: '有 2 筆臨床回饋待審核', time: '昨天', to: '/research/annotation', unread: false },
]

export const auditLog = [
  { time: '今天 09:31', user: '林醫師', action: '修改分級', target: 'EX-1023-06 左腎', result: '成功' },
  { time: '今天 09:02', user: '研究人員', action: '登入', target: '—', result: '成功' },
  { time: '今天 08:12', user: '林醫師', action: '登入', target: '—', result: '成功' },
  { time: '昨天 16:45', user: '林醫師', action: '簽核報告', target: 'R-0011 第 1 版', result: '成功' },
  { time: '昨天 11:20', user: '系統管理者', action: '停用帳號', target: 'intern', result: '成功' },
  { time: '10/22 11:02', user: '林醫師', action: '作廢報告', target: 'R-0007 第 2 版', result: '成功' },
  { time: '10/22 08:01', user: 'researcher', action: '登入', target: '—', result: '密碼錯誤' },
]

export const backups = [
  { time: '今天 03:00', kind: '每日資料庫快照', size: '18 MB', status: '完成' },
  { time: '昨天 03:00', kind: '每日資料庫快照', size: '18 MB', status: '完成' },
  { time: '10/20 18:30', kind: '完整備份（外接硬碟）', size: '4.6 GB', status: '完成' },
]
