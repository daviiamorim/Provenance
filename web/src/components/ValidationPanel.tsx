import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RejectionOut, RunMetrics } from '../api/types'

const LAYER_LABEL: Record<string, string> = {
  syntactic: 'SINTÁTICA',
  numeric: 'NUMÉRICA',
  semantic: 'SEMÂNTICA',
}

const LAYER_COLOR: Record<string, string> = {
  syntactic: 'var(--color-warn)',
  numeric: 'var(--color-fail)',
  semantic: 'var(--color-muted)',
}

function RejectionCard({ r }: { r: RejectionOut }) {
  const layerLabel = LAYER_LABEL[r.layer] ?? r.layer.toUpperCase()
  const layerColor = LAYER_COLOR[r.layer] ?? 'var(--color-muted)'

  const detailEntries = Object.entries(r.detail).filter(
    ([k]) => k !== 'sentence_preview',
  )

  return (
    <article
      className="border-l-[3px] pl-4 py-3 mb-4"
      style={{ borderColor: 'var(--color-fail)' }}
      aria-label={`Rejeição camada ${layerLabel}`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className="font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded border"
          style={{ color: layerColor, borderColor: layerColor }}
        >
          {layerLabel}
        </span>
        <span
          className="font-mono text-[10px]"
          style={{ color: 'var(--color-muted)' }}
        >
          {r.reason_code}
        </span>
        <span
          className="ml-auto font-mono text-[10px]"
          style={{ color: 'var(--color-muted)' }}
        >
          tentativa {r.attempt}
        </span>
      </div>

      <p
        className="font-serif text-[15px] leading-[1.5] italic mb-2"
        style={{ color: 'var(--color-muted)' }}
      >
        {r.text}
      </p>

      {detailEntries.length > 0 && (
        <div
          className="font-mono text-[11px] rounded px-2 py-1.5"
          style={{
            background: 'color-mix(in srgb, var(--color-fail) 8%, transparent)',
            color: 'var(--color-muted)',
          }}
        >
          {detailEntries.map(([k, v]) => (
            <div key={k}>
              <span style={{ color: 'var(--color-text)' }}>{k}</span>
              {': '}
              {String(Array.isArray(v) ? v.join(', ') : v)}
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

function MetricsStrip({ metrics }: { metrics: RunMetrics }) {
  const total = metrics.total_rejections
  const rateOf = (n: number) =>
    total > 0 ? `${((n / total) * 100).toFixed(0)}%` : '—'

  return (
    <div
      className="flex flex-wrap gap-x-8 gap-y-2 py-3 mb-6 border-b"
      style={{ borderColor: 'var(--color-divider)' }}
    >
      <MetricItem label="total de rejeições" value={String(total)} />
      <MetricItem
        label="sintática"
        value={`${metrics.rejections_syntactic} (${rateOf(metrics.rejections_syntactic)})`}
      />
      <MetricItem
        label="numérica"
        value={`${metrics.rejections_numeric} (${rateOf(metrics.rejections_numeric)})`}
      />
      <MetricItem
        label="semântica"
        value={`${metrics.rejections_semantic} (${rateOf(metrics.rejections_semantic)})`}
      />
    </div>
  )
}

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span
        className="font-mono text-[11px] uppercase tracking-wider"
        style={{ color: 'var(--color-muted)' }}
      >
        {label}
      </span>
      <span
        className="font-mono text-sm"
        style={{ color: 'var(--color-accent)' }}
      >
        {value}
      </span>
    </div>
  )
}

export function ValidationPanel({ runId }: { runId: string }) {
  const [rejections, setRejections] = useState<RejectionOut[] | null>(null)
  const [metrics, setMetrics] = useState<RunMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.getValidation(runId), api.getMetrics(runId)])
      .then(([r, m]) => {
        setRejections(r)
        setMetrics(m)
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
  }, [runId])

  if (error) {
    return (
      <p className="font-mono text-sm" style={{ color: 'var(--color-fail)' }}>
        {error}
      </p>
    )
  }

  if (!rejections || !metrics) {
    return (
      <p className="font-mono text-sm" style={{ color: 'var(--color-muted)' }}>
        carregando…
      </p>
    )
  }

  return (
    <section aria-label="Painel de validação">
      <MetricsStrip metrics={metrics} />

      {rejections.length === 0 ? (
        <p
          className="font-mono text-sm"
          style={{ color: 'var(--color-muted)' }}
        >
          nenhuma rejeição registrada nesta execução
        </p>
      ) : (
        <div>
          {rejections.map((r) => (
            <RejectionCard key={r.id} r={r} />
          ))}
        </div>
      )}
    </section>
  )
}
