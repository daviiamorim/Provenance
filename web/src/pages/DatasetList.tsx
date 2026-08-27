import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { DatasetOut } from '../api/types'

function datasetLabel(d: DatasetOut): string {
  return d.manifest[0]?.path ?? d.id
}

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))
}

function UploadZone({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file: File) {
    setUploading(true)
    setUploadError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/datasets/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText)
        throw new Error(`${res.status} ${text}`)
      }
      onUploaded()
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) void handleFile(file)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) void handleFile(file)
  }

  return (
    <div className="mb-10">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        disabled={uploading}
        className="w-full border-2 border-dashed rounded-lg px-6 py-8 text-center transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        style={{
          borderColor: dragging ? 'var(--color-accent)' : 'var(--color-divider)',
          background: dragging ? 'color-mix(in srgb, var(--color-accent) 6%, transparent)' : 'transparent',
        }}
      >
        <p className="font-mono text-sm text-[var(--color-accent)] mb-1">
          {uploading ? 'enviando…' : '+ enviar dataset'}
        </p>
        <p className="font-mono text-[11px] text-[var(--color-muted)]">
          arraste um arquivo CSV aqui ou clique para selecionar
        </p>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv,.parquet,.zip"
        className="hidden"
        onChange={onInputChange}
        aria-label="Selecionar arquivo para upload"
      />

      {uploadError && (
        <p className="font-mono text-[11px] text-[var(--color-fail)] mt-2">{uploadError}</p>
      )}
    </div>
  )
}

export function DatasetList() {
  const [datasets, setDatasets] = useState<DatasetOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  function loadDatasets() {
    api.listDatasets()
      .then(setDatasets)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }

  useEffect(() => {
    loadDatasets()
  }, [])

  async function handleSelect(d: DatasetOut) {
    try {
      const runs = await api.listRuns(d.id)
      if (runs.length === 0) {
        setError(`Nenhuma execução encontrada para ${datasetLabel(d)}.`)
        return
      }
      const latest = runs.reduce((a, b) =>
        a.created_at > b.created_at ? a : b
      )
      navigate(`/report/${latest.id}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <main className="max-w-2xl mx-auto px-6 py-16">
      <h1 className="font-sans text-2xl font-semibold text-[var(--color-text)] mb-1">
        Provenance
      </h1>
      <p className="font-mono text-xs text-[var(--color-muted)] mb-10 uppercase tracking-wider">
        análise de datasets com cadeia de evidências
      </p>

      <UploadZone onUploaded={loadDatasets} />

      {error && (
        <p className="font-mono text-sm text-[var(--color-fail)] mb-6">{error}</p>
      )}

      {datasets === null && !error && (
        <p className="font-mono text-sm text-[var(--color-muted)]">carregando…</p>
      )}

      {datasets !== null && datasets.length > 0 && (
        <>
          <p className="font-mono text-[11px] text-[var(--color-muted)] uppercase tracking-wider mb-3">
            datasets processados
          </p>
          <ul className="divide-y divide-[var(--color-divider)]">
            {datasets.map((d) => (
              <li key={d.id}>
                <button
                  onClick={() => void handleSelect(d)}
                  className="w-full text-left py-4 group flex items-baseline gap-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] rounded"
                >
                  <span className="font-sans text-base text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors">
                    {datasetLabel(d)}
                  </span>
                  <span className="font-mono text-[11px] text-[var(--color-muted)] ml-auto shrink-0">
                    {formatDate(d.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {datasets !== null && datasets.length === 0 && (
        <p className="font-mono text-sm text-[var(--color-muted)]">
          nenhum dataset processado ainda — envie um arquivo acima
        </p>
      )}
    </main>
  )
}
