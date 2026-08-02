import { FileArchive, FolderOpen, ImagePlus, UploadCloud, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { formatBytes } from '../lib/format'

interface DropzoneProps {
  files: File[]
  onFiles: (files: File[]) => void
  accept?: string
  multiple?: boolean
  directory?: boolean
  disabled?: boolean
  title?: string
  description?: string
}

export function Dropzone({
  files, onFiles, accept = 'image/*,.jfif,.zip', multiple = true, directory = false, disabled = false,
  title = '拖放圖片或 ZIP 到此處', description = '也可以點擊選擇檔案；資料只會送到本機服務。',
}: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const append = (incoming: FileList | File[]) => {
    const next = [...files]
    for (const file of Array.from(incoming)) {
      const key = `${file.name}-${file.size}-${file.lastModified}`
      if (!next.some((item) => `${item.name}-${item.size}-${item.lastModified}` === key)) next.push(file)
    }
    onFiles(multiple ? next : next.slice(-1))
  }

  const directoryAttributes = directory ? ({ webkitdirectory: '', directory: '' } as Record<string, string>) : {}

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => { event.preventDefault(); if (!disabled) setDragging(true) }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false) }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled) append(event.dataTransfer.files) }}
        className={`group flex min-h-40 w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition ${dragging ? 'border-clinical-500 bg-clinical-50' : 'border-slate-300 bg-slate-50/70 hover:border-clinical-400 hover:bg-clinical-50/50'} disabled:cursor-not-allowed disabled:opacity-50`}
      >
        <div className="mb-3 rounded-2xl bg-white p-3 text-clinical-700 shadow-sm ring-1 ring-slate-200">
          {directory ? <FolderOpen className="h-6 w-6" /> : <UploadCloud className="h-6 w-6" />}
        </div>
        <span className="font-semibold text-slate-800">{title}</span>
        <span className="mt-1 text-xs leading-5 text-slate-500">{description}</span>
      </button>
      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(event) => { if (event.target.files) append(event.target.files); event.target.value = '' }}
        {...directoryAttributes}
      />
      {files.length > 0 && (
        <div className="mt-3 space-y-2">
          {files.slice(0, 6).map((file, index) => (
            <div key={`${file.name}-${file.lastModified}`} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm">
              {file.name.toLowerCase().endsWith('.zip') ? <FileArchive className="h-4 w-4 text-amber-600" /> : <ImagePlus className="h-4 w-4 text-clinical-600" />}
              <span className="min-w-0 flex-1 truncate font-medium text-slate-700">{file.name}</span>
              <span className="shrink-0 text-xs text-slate-400">{formatBytes(file.size)}</span>
              <button type="button" className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600" aria-label={`移除 ${file.name}`} onClick={() => onFiles(files.filter((_, itemIndex) => itemIndex !== index))}><X className="h-4 w-4" /></button>
            </div>
          ))}
          {files.length > 6 && <p className="text-center text-xs text-slate-500">另有 {files.length - 6} 個檔案</p>}
        </div>
      )}
    </div>
  )
}
