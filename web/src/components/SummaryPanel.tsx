import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RunMetrics } from '../api/types'

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <div
      className="rounded px-4 py-3 border"
      style={{ borderColor: 'var(--color-divider)' }}
    >
      <div
        className="font-mono text-[28px] font-semibold leading-none mb-1"
        style={{ color: 'var(--color-accent)' }}
      >
        {value.toLocaleString('pt-BR')}
      </div>
      <div
        className="font-mono text-[11px] uppercase tracking-wider"
        style={{ color: 'var(--color-muted)' }}
      >
        {label}
      </div>
    </div>
  )
}

function SeverityRow({
  label,
  value,
  color,
}: {
  label: string
  value: number
  color: string
}) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="font-mono text-[11px] uppercase tracking-wider min-w-[7rem]"
        style={{ color }}
      >
        {label}
      </span>
      <span className="font-mono text-lg" style={{ color: 'var(--color-text)' }}>
        {value.toLocaleString('pt-BR')}
      </span>
    </div>
  )
}

export function SummaryPanel({ runId }: { runId: string }) {
  const [metrics, setMetrics] = useState<RunMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getMetrics(runId)
      .then(setMetrics)
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

  if (!metrics) {
    return (
      <p className="font-mono text-sm" style={{ color: 'var(--color-muted)' }}>
        carregando…
      </p>
    )
  }

  const { counts, severity } = metrics

  return (
    <section aria-label="Resumo da execução">
      <p
        className="font-mono text-[11px] uppercase tracking-widest mb-3"
        style={{ color: 'var(--color-muted)' }}
      >
        camadas
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
        <CountCard label="measurements" value={counts.measurements} />
        <CountCard label="findings" value={counts.findings} />
        <CountCard label="assessments" value={counts.assessments} />
        <CountCard label="afirmações aprovadas" value={counts.claims_passed} />
      </div>

      <p
        className="font-mono text-[11px] uppercase tracking-widest mb-3"
        style={{ color: 'var(--color-muted)' }}
      >
        verificações por severidade (findings)
      </p>
      <div
        className="flex flex-col gap-2 mb-8 border-l-2 pl-4"
        style={{ borderColor: 'var(--color-divider)' }}
      >
        <SeverityRow label="OK" value={severity.ok} color="var(--color-ok)" />
        <SeverityRow
          label="WARN"
          value={severity.warn}
          color="var(--color-warn)"
        />
        <SeverityRow
          label="FAIL"
          value={severity.fail}
          color="var(--color-fail)"
        />
      </div>

      <p
        className="font-mono text-[11px] uppercase tracking-widest mb-3"
        style={{ color: 'var(--color-muted)' }}
      >
        validação de afirmações
      </p>
      <div
        className="flex flex-col gap-2 border-l-2 pl-4"
        style={{ borderColor: 'var(--color-divider)' }}
      >
        <SeverityRow
          label="total de rejeições"
          value={metrics.total_rejections}
          color="var(--color-muted)"
        />
        <SeverityRow
          label="sintática"
          value={metrics.rejections_syntactic}
          color="var(--color-muted)"
        />
        <SeverityRow
          label="numérica"
          value={metrics.rejections_numeric}
          color="var(--color-muted)"
        />
        <SeverityRow
          label="semântica"
          value={metrics.rejections_semantic}
          color="var(--color-muted)"
        />
      </div>
    </section>
  )
}
