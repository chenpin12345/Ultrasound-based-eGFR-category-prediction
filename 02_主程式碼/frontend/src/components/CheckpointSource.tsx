import type { CheckpointSource as Source } from '../types/api'

export function CheckpointSource({source}:{source:Source}) {
  const verified=source.status==='verified_record'
  return <section className="mt-4 space-y-3 rounded-lg border border-slate-200 p-4" aria-label="Checkpoint 來源證據">
    <h3 className="font-semibold">{verified?'Checkpoint 來源紀錄已核對':'Checkpoint 來源尚未核實'}</h3>
    <p className="text-sm">{source.reason}</p>
    {verified&&<><p className="text-sm">輸入共 {source.sample_count} 張；{Object.entries(source.split_counts||{}).map(([key,count])=>`${key} ${count} 張`).join(' · ')}。沒有 test 樣本時，不顯示 0% 測試成績。</p>
      <div className="grid gap-3 sm:grid-cols-2"><div><h4 className="font-semibold">選中的最佳 checkpoint</h4><p>Epoch {source.best_epoch_record?.epoch} · validation loss {source.selection?.value}</p><p>{source.selection?.selected_fold==null?'單一切分':`選中 fold ${source.selection.selected_fold+1}`}</p></div><div><h4 className="font-semibold">最後 epoch 訓練紀錄</h4><p>Epoch {source.last_epoch_record?.epoch}</p><p className="text-sm">此處不是最佳權重成績。</p></div></div>
      <details><summary className="cursor-pointer py-2">查看最佳／最後 epoch 各項原始指標</summary><pre className="overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify({best:source.best_epoch_record,last:source.last_epoch_record},null,2)}</pre></details>
      {source.cross_validation&&<details><summary className="cursor-pointer py-2">各 fold 與歷史聚合（不等同選中 checkpoint）</summary><p className="text-sm">validation 聚合沿用各 fold 最後 epoch 的原始訓練紀錄，不標示成最佳權重平均準確率。</p><pre className="overflow-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(source.cross_validation,null,2)}</pre></details>}
      <p className="break-all text-xs text-slate-600">來源 SHA-256：{source.sha256}；輸入清單：{source.samples_sha256}</p></>}
  </section>
}
