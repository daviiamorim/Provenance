import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ClaimSummary, ReportOut, ReportSection } from '../api/types'
import { SeverityBadge } from '../components/SeverityBadge'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { ValidationPanel } from '../components/ValidationPanel'
import { SummaryPanel } from '../components/SummaryPanel'

type Tab = 'report' | 'validation' | 'summary'

const TAB_LABELS: Record<Tab, string> = {
  summary: 'Resumo',
  report: 'Laudo',
  validation: 'Validação',
}

const TABS: Tab[] = ['summary', 'report', 'validation']

const GOAL_LABELS: Record<string, string> = {
  data_quality: 'QUALIDADE',
  modeling_readiness: 'MODELAGEM',
  general: 'GERAL',
}

function goalLabel(goal: string): string {
  return GOAL_LABELS[goal] ?? goal.toUpperCase().replace(/_/g, ' ')
}

function ClaimRow({
  claim,
  onOpenChain,
}: {
  claim: ClaimSummary
  onOpenChain: (id: string) => void
}) {
  const fnds = claim.supports.filter((s) => s.startsWith('fnd-'))
  const asts = claim.supports.filter((s) => s.startsWith('ast-'))

  return (
    <button
      type="button"
      className="w-full text-left grid grid-cols-[6rem_1fr] gap-x-6 gap-y-0 py-5 border-b border-[var(--color-divider)] last:border-b-0 items-start hover:bg-[var(--color-raised)] transition-colors cursor-pointer"
      onClick={() => onOpenChain(claim.id)}
      aria-label={`Ver cadeia de evidências: ${claim.text.slice(0, 80)}`}
    >
      <div className="pt-1 flex flex-col gap-1.5">
        <SeverityBadge severity={claim.severity} />
      </div>

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
    </button>
  )
}

function Section({
  section,
  onOpenChain,
}: {
  section: ReportSection
  onOpenChain: (id: string) => void
}) {
  return (
    <section aria-label={goalLabel(section.goal)} className="mb-10">
      <p className="font-mono text-[11px] text-[var(--color-muted)] uppercase tracking-widest mb-1">
        {goalLabel(section.goal)}
      </p>
      <div className="border-t border-[var(--color-divider)]">
        {section.claims.map((c) => (
          <ClaimRow key={c.id} claim={c} onOpenChain={onOpenChain} />
        ))}
      </div>
    </section>
  )
}

function TabNav({
  activeTab,
  onChange,
}: {
  activeTab: Tab
  onChange: (t: Tab) => void
}) {
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  function handleKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (idx + 1) % TABS.length
      tabRefs.current[next]?.focus()
      onChange(TABS[next])
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prev = (idx - 1 + TABS.length) % TABS.length
      tabRefs.current[prev]?.focus()
      onChange(TABS[prev])
    } else if (e.key === 'Home') {
      e.preventDefault()
      tabRefs.current[0]?.focus()
      onChange(TABS[0])
    } else if (e.key === 'End') {
      e.preventDefault()
      tabRefs.current[TABS.length - 1]?.focus()
      onChange(TABS[TABS.length - 1])
    }
  }

  return (
    <nav
      role="tablist"
      aria-label="Visões do laudo"
      className="flex gap-0 border-b border-[var(--color-divider)] mb-8"
    >
      {TABS.map((tab, idx) => {
        const isActive = tab === activeTab
        return (
          <button
            key={tab}
            ref={(el) => {
              tabRefs.current[idx] = el
            }}
            role="tab"
            aria-selected={isActive}
            aria-controls={`panel-${tab}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className="px-4 py-2.5 font-mono text-[12px] uppercase tracking-wider transition-colors relative"
            style={{
              color: isActive ? 'var(--color-accent)' : 'var(--color-muted)',
              borderTop: 'none',
              borderLeft: 'none',
              borderRight: 'none',
              borderBottom: isActive
                ? '2px solid var(--color-accent)'
                : '2px solid transparent',
              marginBottom: '-1px',
              background: 'none',
              cursor: 'pointer',
            }}
          >
            {TAB_LABELS[tab]}
          </button>
        )
      })}
    </nav>
  )
}

export function Report() {
  const { runId } = useParams<{ runId: string }>()
  const [report, setReport] = useState<ReportOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('summary')

  useEffect(() => {
    if (!runId) return
    api
      .getReport(runId)
      .then(setReport)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
  }, [runId])

  if (error) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-16">
        <Link
          to="/"
          className="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] mb-8 inline-block"
        >
          ← datasets
        </Link>
        <p className="font-mono text-sm text-[var(--color-fail)]">{error}</p>
      </main>
    )
  }

  if (!report) {
    return (
      <main className="max-w-2xl mx-auto px-6 py-16">
        <p className="font-mono text-sm text-[var(--color-muted)]">
          carregando…
        </p>
      </main>
    )
  }

  const { counts } = report

  return (
    <>
      <main className="max-w-2xl mx-auto px-6 py-12">
        <Link
          to="/"
          className="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors mb-10 inline-block"
        >
          ← datasets
        </Link>

        <header className="mb-8">
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

        <TabNav activeTab={activeTab} onChange={setActiveTab} />

        <div
          id="panel-report"
          role="tabpanel"
          aria-labelledby="tab-report"
          hidden={activeTab !== 'report'}
        >
          {report.sections.length === 0 ? (
            <p className="font-mono text-sm text-[var(--color-muted)]">
              nenhuma afirmação aprovada nesta execução
            </p>
          ) : (
            report.sections.map((s) => (
              <Section key={s.goal} section={s} onOpenChain={setSelectedClaimId} />
            ))
          )}
        </div>

        <div
          id="panel-validation"
          role="tabpanel"
          aria-labelledby="tab-validation"
          hidden={activeTab !== 'validation'}
        >
          {runId && <ValidationPanel runId={runId} />}
        </div>

        <div
          id="panel-summary"
          role="tabpanel"
          aria-labelledby="tab-summary"
          hidden={activeTab !== 'summary'}
        >
          {runId && <SummaryPanel runId={runId} />}
        </div>
      </main>

      <EvidenceDrawer
        claimId={selectedClaimId}
        onClose={() => setSelectedClaimId(null)}
      />
    </>
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
