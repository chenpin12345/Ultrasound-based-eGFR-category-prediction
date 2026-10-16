import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card, InlineNotice, PageHeader, StatePanel } from '../components/ui'
import { useAsyncResource } from '../hooks/useAsyncResource'
import { api } from '../lib/api'
import { ModelEvaluation } from '../components/ModelEvaluation'
import { CheckpointSource } from '../components/CheckpointSource'

export function ModelDetailPage() {
  const {modelId=''}=useParams()
  const load=useCallback((signal?:AbortSignal)=>api.getModel(modelId,signal),[modelId])
  const resource=useAsyncResource(load,Boolean(modelId),`model-detail:${modelId}`)
  const model=resource.data
  return <div className="space-y-5">
    <PageHeader title={model?.name||'模型詳情'} description="權重、設定與引用分別列示；訓練紀錄不等於指定權重的評估成績。" actions={<Link className="btn-secondary" to="/model-center/models">返回模型管理</Link>}/>
    {resource.updateError&&<InlineNotice tone="danger">背景更新失敗：{resource.updateError}</InlineNotice>}
    <StatePanel loading={resource.loading} error={resource.error} onRetry={()=>void resource.refresh()}>
      {model&&<div className="space-y-5">
        <Card className="p-5"><h2 className="section-title">權重識別與輸出順序</h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2"><div><dt>架構／任務</dt><dd>{model.architecture} · {model.task==='segmentation'?'分割':`${model.class_count} 分類`}</dd></div><div><dt>版本</dt><dd>{model.version}</dd></div><div className="sm:col-span-2"><dt>登錄的權重 SHA-256</dt><dd className="break-all font-mono text-sm">{model.sha256}</dd></div></dl>
          <ol className="mt-4 list-inside list-decimal space-y-1">{model.class_schema.class_names.map((name,index)=><li key={index}>{name}<span className="ml-2 text-sm text-slate-500">輸出索引 {index}</span></li>)}</ol>
          <p className="mt-3 break-all text-xs text-slate-500">類別契約 {model.class_schema.version} · {model.class_schema.sha256}</p>
        </Card>
        <Card className="p-5"><h2 className="section-title">每份模型專屬設定</h2><p className="mt-2">{model.configuration.status==='consistent'?'設定與登錄資料一致（不代表已重現準確率）':'設定未核實'}</p>
          {model.configuration.reason&&<InlineNotice tone="warning">{model.configuration.reason}</InlineNotice>}
          <p className="mt-3">MLP 欄位順序：{model.metadata_columns.length?model.metadata_columns.join(' → '):'此模型不使用 MLP 欄位'}</p>
          <details className="mt-3"><summary className="cursor-pointer py-3 font-semibold">前處理與正規化設定</summary><pre className="overflow-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify({preprocessing:model.preprocessing,train_stats:model.configuration.train_stats},null,2)}</pre></details>
          <p className="mt-2 break-all text-xs text-slate-500">設定 SHA-256：{model.configuration.sha256||'無法核實'}</p>
        </Card>
        <Card className="p-5"><h2 className="section-title">來源與成績</h2><p className="mt-2">{model.source_info.status==='verified_record'?'訓練來源紀錄已核對':'來源未核實'}：{model.source_info.reason}</p>
          <p className="mt-2 text-sm text-slate-600">不以檔名、最後 epoch 或單張機率推測模型準確率；海報成績尚未驗證重現。</p>
          <div className="mt-4 rounded-lg bg-slate-50 p-4"><ModelEvaluation summary={model.evaluation_summary} details/></div>
          <Link className="btn-secondary mt-3" to={`/model-center/evaluations?model_id=${model.id}`}>選擇資料並建立評估</Link>
          {model.training_record&&<div className="mt-4 rounded-lg bg-slate-50 p-4"><p>訓練選模依據：最低 validation loss</p><p>紀錄值：{model.training_record.recorded_best_validation_loss??'無紀錄'}；已完成 epoch：{model.training_record.completed_epoch}</p><p className="mt-2 text-sm">{model.training_record.note}</p><Link className="btn-secondary mt-3" to={`/model-center/training/${model.training_record.training_job_id}`}>查看訓練紀錄</Link></div>}
          {model.training_record?.checkpoint_source&&<CheckpointSource source={model.training_record.checkpoint_source}/>}
        </Card>
        <Card className="p-5"><h2 className="section-title">引用與刪除限制</h2><p className="mt-2 text-sm">有研究工作、醫師封存方案或預設設定引用時，保留模型以便追溯。</p>
          {model.references.length?<ul className="mt-3 divide-y">{model.references.map(ref=><li key={`${ref.kind}:${ref.id}`} className="py-3"><span className="font-semibold">{ref.name}</span> · {ref.status}<p className="break-all text-xs text-slate-500">{ref.kind} · {ref.id}</p></li>)}</ul>:<p className="mt-3">目前沒有引用；提交刪除時仍會重新檢查。</p>}
        </Card>
      </div>}
    </StatePanel>
  </div>
}
