import { useEffect, useState } from 'react'
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

export function DatasetList() {
  const [datasets, setDatasets] = useState<DatasetOut[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.listDatasets()
      .then(setDatasets)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
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
        data-observatory
      </h1>
      <p className="font-mono text-xs text-[var(--color-muted)] mb-10 uppercase tracking-wider">
        datasets processados
      </p>

      {error && (
        <p className="font-mono text-sm text-[var(--color-fail)] mb-6">{error}</p>
      )}

      {datasets === null && !error && (
        <p className="font-mono text-sm text-[var(--color-muted)]">carregando…</p>
      )}

      {datasets !== null && datasets.length === 0 && (
        <p className="font-mono text-sm text-[var(--color-muted)]">
          nenhum dataset processado ainda
        </p>
      )}

      {datasets !== null && datasets.length > 0 && (
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
      )}
    </main>
  )
}
