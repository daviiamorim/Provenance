import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ClaimSummary, ReportOut, ReportSection } from '../api/types'
import { SeverityBadge } from '../components/SeverityBadge'

const GOAL_LABELS: Record<string, string> = {
  data_quality: 'QUALIDADE',
  modeling_readiness: 'MODELAGEM',
  general: 'GERAL',
}

function goalLabel(goal: string): string {
  return GOAL_LABELS[goal] ?? goal.toUpperCase().replace(/_/g, ' ')
}

function ClaimRow({ claim }: { claim: ClaimSummary }) {
  const fnds = claim.supports.filter((s) => s.startsWith('fnd-'))
  const asts = claim.supports.filter((s) => s.startsWith('ast-'))

  return (
    <div className="grid grid-cols-[6rem_1fr] gap-x-6 gap-y-0 py-5 border-b border-[var(--color-divider)] last:border-b-0 items-start">
      {/* left column: severity badge */}
      <div className="pt-1 flex flex-col gap-1.5">
        <SeverityBadge severity={claim.severity} />
      </div>

      {/* right column: text + source tags */}
      <div>
        <p className="font-serif text-[18px] leading-[1.55] text-[var(--color-text)] mb-2.5">
          {claim.text}
        </p>
        <div className="flex flex-wrap gap-1.5" aria-label="fontes">
          {fnds.map((id) => (
            <span
              key={id}
              className="font-mono text-[11px] text-[var(--color-accent)] border border-[var(--color-divider)] rounded px-1.5 py-0.5"
            >
              {id}
            </span>
          ))}
          {asts.map((id) => (
            <span
              key={id}
              className="font-mono text-[11px] text-[var(--color-muted)] border border-[var(--color-divider)] rounded px-1.5 py-0.5"
            >
              {id}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function Section({ section }: { section: ReportSection }) {
  return (
    <section aria-label={goalLabel(section.goal)} className="mb-10">
      <p className="font-mono text-[11px] text-[var(--color-muted)] uppercase tracking-widest mb-1">
        {goalLabel(section.goal)}
      </p>
      <div className="border-t border-[var(--color-divider)]">
        {section.claims.map((c) => (
          <ClaimRow key={c.id} claim={c} />
        ))}
      </div>
    </section>
  )
}

export function Report() {
  const { runId } = useParams<{ runId: string }>()
  const [report, setReport] = useState<ReportOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    api.getReport(runId)
      .then(setReport)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [runId])

  if (error) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-16">
        <Link to="/" className="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] mb-8 inline-block">
          ← datasets
        </Link>
        <p className="font-mono text-sm text-[var(--color-fail)]">{error}</p>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-16">
        <p className="font-mono text-sm text-[var(--color-muted)]">carregando…</p>
      </main>
    )
  }

  const { counts } = report

  return (
    <main className="max-w-2xl mx-auto px-6 py-12">
      <Link
        to="/"
        className="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors mb-10 inline-block"
      >
        ← datasets
      </Link>

      {/* Header */}
      <header className="mb-10">
        <h1 className="font-sans text-2xl font-semibold text-[var(--color-text)] mb-3">
          {report.dataset_name}
        </h1>
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          {counts.rows !== null && (
            <Stat label="linhas" value={counts.rows.toLocaleString('pt-BR')} />
          )}
          <Stat label="colunas" value={String(counts.columns)} />
          <Stat label="findings" value={String(counts.findings)} />
          <Stat label="afirmações" value={String(counts.claims)} />
        </div>
      </header>

      {/* Body */}
      {report.sections.length === 0 ? (
        <p className="font-mono text-sm text-[var(--color-muted)]">
          nenhuma afirmação aprovada nesta execução
        </p>
      ) : (
        report.sections.map((s) => <Section key={s.goal} section={s} />)
      )}
    </main>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-mono text-[11px] text-[var(--color-muted)] uppercase tracking-wider">
        {label}
      </span>
      <span className="font-mono text-sm text-[var(--color-accent)]">{value}</span>
    </div>
  )
}
