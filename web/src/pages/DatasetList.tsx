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

type UploadStep = 'idle' | 'uploading' | 'analyzing'

function UploadZone({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const [step, setStep] = useState<UploadStep>('idle')
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file: File) {
    setStep('uploading')
    setUploadError(null)
    try {
      const { dataset_id } = await api.uploadDataset(file)
      setStep('analyzing')
      const { run_id } = await api.createRun(dataset_id)
      onUploaded()
      navigate(`/report/${run_id}`)
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e))
      setStep('idle')
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
        disabled={step !== 'idle'}
        className="w-full rounded-lg px-6 py-8 text-center transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
          background: dragging ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : 'transparent',
        }}
      >
        <p className="font-mono text-sm mb-1" style={{ color: 'var(--accent)' }}>
          {step === 'uploading' && 'enviando arquivo…'}
          {step === 'analyzing' && 'analisando dataset…'}
          {step === 'idle' && '+ enviar dataset'}
        </p>
        <p className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {step === 'analyzing'
            ? 'isso pode levar alguns segundos'
            : 'arraste um CSV aqui ou clique para selecionar'}
        </p>
      </button>

      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv,.parquet,.zip"
        className="hidden"
        onChange={onInputChange}
        disabled={step !== 'idle'}
        aria-label="Selecionar arquivo para upload"
      />

      {uploadError && (
        <p className="font-mono mt-2" style={{ fontSize: '11px', color: 'var(--fail-fg)' }}>
          {uploadError}
        </p>
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

  useEffect(() => { loadDatasets() }, [])

  async function handleSelect(d: DatasetOut) {
    try {
      const runs = await api.listRuns(d.id)
      if (runs.length === 0) {
        setError(`Nenhuma execução encontrada para ${datasetLabel(d)}.`)
        return
      }
      const latest = runs.reduce((a, b) => a.created_at > b.created_at ? a : b)
      navigate(`/report/${latest.id}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <main className="max-w-2xl mx-auto px-6 py-16">
      <h1 className="font-sans font-semibold mb-1" style={{ fontSize: '19px', color: 'var(--text-primary)' }}>
        Provenance
      </h1>
      <p className="font-mono mb-10 uppercase" style={{ fontSize: '10px', letterSpacing: '0.09em', color: 'var(--text-muted)' }}>
        análise de datasets com cadeia de evidências
      </p>

      <UploadZone onUploaded={loadDatasets} />

      {error && (
        <p className="font-mono text-sm mb-6" style={{ color: 'var(--fail-fg)' }}>
          {error}
        </p>
      )}

      {datasets === null && !error && (
        <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>carregando…</p>
      )}

      {datasets !== null && datasets.length > 0 && (
        <>
          <p className="font-mono uppercase mb-3" style={{ fontSize: '10px', letterSpacing: '0.09em', color: 'var(--text-muted)' }}>
            datasets processados
          </p>
          <ul style={{ borderTop: '0.5px solid var(--border)' }}>
            {datasets.map((d) => (
              <li key={d.id} style={{ borderBottom: '0.5px solid var(--border)' }}>
                <button
                  onClick={() => void handleSelect(d)}
                  className="w-full text-left py-4 flex items-baseline gap-4 transition-colors"
                  style={{ background: 'none', cursor: 'pointer', border: 'none' }}
                >
                  <span
                    className="font-sans text-base transition-colors"
                    style={{ color: 'var(--text-primary)' }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-primary)' }}
                  >
                    {datasetLabel(d)}
                  </span>
                  <span className="font-mono ml-auto shrink-0" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {formatDate(d.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {datasets !== null && datasets.length === 0 && (
        <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>
          nenhum dataset processado ainda — envie um arquivo acima
        </p>
      )}
    </main>
  )
}
