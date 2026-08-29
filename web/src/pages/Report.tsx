import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ClaimSummary, ReportOut, ReportSection, RunMetrics } from '../api/types'
import { SeverityBadge } from '../components/SeverityBadge'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { ValidationPanel } from '../components/ValidationPanel'
import { SummaryPanel } from '../components/SummaryPanel'

type Tab = 'summary' | 'report' | 'validation'

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

// ── Brand mark ────────────────────────────────────────────────────────────────

function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
      <rect width="22" height="22" rx="4" fill="#1d9e75" opacity="0.12" />
      <rect x="3" y="3.5" width="16" height="2.5" rx="1" fill="#1d9e75" opacity="0.25" />
      <rect x="3" y="8" width="16" height="2.5" rx="1" fill="#1d9e75" opacity="0.5" />
      <rect x="3" y="12.5" width="16" height="2.5" rx="1" fill="#1d9e75" opacity="0.75" />
      <rect x="3" y="17" width="16" height="2.5" rx="1" fill="#1d9e75" />
    </svg>
  )
}

// ── Evidence chain layer labels ───────────────────────────────────────────────

const LAYERS = [
  { name: 'MEDIÇÃO',   color: 'var(--layer-1)' },
  { name: 'FINDING',   color: 'var(--layer-2)' },
  { name: 'AVALIAÇÃO', color: 'var(--layer-3)' },
  { name: 'AFIRMAÇÃO', color: 'var(--layer-4)' },
] as const

function LayerTag({ name, color }: { name: string; color: string }) {
  return (
    <div
      className="font-mono uppercase pl-2"
      style={{
        borderLeft: `2px solid ${color}`,
        fontSize: '10px',
        letterSpacing: '0.09em',
        lineHeight: '1.4',
        color: 'var(--text-muted)',
      }}
    >
      {name}
    </div>
  )
}

// ── Claim row ─────────────────────────────────────────────────────────────────

function ClaimRow({
  claim,
  index,
  onOpenChain,
}: {
  claim: ClaimSummary
  index: number
  onOpenChain: (id: string) => void
}) {
  return (
    <button
      type="button"
      className="claim-enter w-full text-left"
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0,128px) minmax(0,1fr)',
        gap: '16px',
        paddingTop: '15px',
        paddingBottom: '15px',
        borderTop: '0.5px solid var(--border)',
        animationDelay: `${index * 400}ms`,
        background: 'none',
        cursor: 'pointer',
      }}
      onClick={() => onOpenChain(claim.id)}
      aria-label={`Ver evidências: ${claim.text.slice(0, 80)}`}
    >
      {/* Left: evidence chain layers */}
      <div className="flex flex-col gap-2 pt-0.5">
        {LAYERS.map((l) => (
          <LayerTag key={l.name} name={l.name} color={l.color} />
        ))}
      </div>

      {/* Right: 3-level text */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-1.5">
          <p style={{ fontSize: '15px', lineHeight: '1.55', color: 'var(--text-primary)', margin: 0 }}>
            {claim.text}
          </p>
          <SeverityBadge severity={claim.severity} />
        </div>
        {claim.explanation && (
          <p style={{ fontSize: '12.5px', lineHeight: '1.5', color: 'var(--text-secondary)', margin: '0 0 8px' }}>
            {claim.explanation}
          </p>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {claim.supports.map((id) => (
            <span
              key={id}
              className="font-mono"
              style={{ fontSize: '10px', color: 'var(--text-faint)' }}
            >
              {id}
            </span>
          ))}
        </div>
      </div>
    </button>
  )
}

// ── Claims view with 3 error states ──────────────────────────────────────────

function RejectionCount({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="font-mono uppercase min-w-[5rem]"
        style={{ fontSize: '10px', letterSpacing: '0.09em', color: 'var(--text-muted)' }}
      >
        {label}
      </span>
      <span className="font-mono text-sm" style={{ color: 'var(--text-primary)' }}>
        {value}
      </span>
    </div>
  )
}

function ClaimsView({
  sections,
  metrics,
  onOpenChain,
}: {
  sections: ReportSection[]
  metrics: RunMetrics | null
  onOpenChain: (id: string) => void
}) {
  const totalClaims = sections.reduce((sum, s) => sum + s.claims.length, 0)

  if (totalClaims === 0) {
    const totalRejections = metrics?.total_rejections ?? 0

    if (totalRejections > 0) {
      return (
        <div style={{ borderTop: '0.5px solid var(--border)', paddingTop: '24px' }}>
          <p style={{ fontSize: '15px', lineHeight: '1.55', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Nenhuma afirmação passou na validação.
          </p>
          <div className="flex flex-col gap-2">
            <RejectionCount label="sintática"  value={metrics!.rejections_syntactic} />
            <RejectionCount label="numérica"   value={metrics!.rejections_numeric} />
            <RejectionCount label="semântica"  value={metrics!.rejections_semantic} />
          </div>
        </div>
      )
    }

    return (
      <div style={{ borderTop: '0.5px solid var(--border)', paddingTop: '24px' }}>
        <p style={{ fontSize: '15px', lineHeight: '1.55', color: 'var(--fail-fg)', marginBottom: '8px' }}>
          Não foi possível gerar as afirmações.
        </p>
        <p className="font-mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          verifique se ANTHROPIC_API_KEY está configurada no servidor
        </p>
      </div>
    )
  }

  let claimIndex = 0
  return (
    <>
      {sections.map((s) => (
        <section key={s.goal} aria-label={goalLabel(s.goal)} className="mb-10">
          <p
            className="font-mono uppercase mb-2"
            style={{ fontSize: '10px', letterSpacing: '0.09em', color: 'var(--text-muted)' }}
          >
            {goalLabel(s.goal)}
          </p>
          {s.claims.map((c) => {
            const idx = claimIndex++
            return (
              <ClaimRow key={c.id} claim={c} index={idx} onOpenChain={onOpenChain} />
            )
          })}
        </section>
      ))}
    </>
  )
}

// ── Tab navigation ────────────────────────────────────────────────────────────

function TabNav({ activeTab, onChange }: { activeTab: Tab; onChange: (t: Tab) => void }) {
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
    }
  }

  return (
    <nav role="tablist" aria-label="Visões do laudo" className="flex mb-8" style={{ borderBottom: '0.5px solid var(--border)' }}>
      {TABS.map((tab, idx) => {
        const isActive = tab === activeTab
        return (
          <button
            key={tab}
            ref={(el) => { tabRefs.current[idx] = el }}
            role="tab"
            aria-selected={isActive}
            aria-controls={`panel-${tab}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className="font-mono uppercase transition-colors"
            style={{
              fontSize: '10px',
              letterSpacing: '0.09em',
              padding: '10px 16px',
              color: isActive ? 'var(--accent)' : 'var(--text-muted)',
              border: 'none',
              borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
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

// ── Main Report page ──────────────────────────────────────────────────────────

export function Report() {
  const { runId } = useParams<{ runId: string }>()
  const [report, setReport] = useState<ReportOut | null>(null)
  const [metrics, setMetrics] = useState<RunMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('summary')

  useEffect(() => {
    if (!runId) return
    api.getReport(runId)
      .then(setReport)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
    api.getMetrics(runId)
      .then(setMetrics)
      .catch(() => {/* metrics are optional for error states */})
  }, [runId])

  const isLoading = !report && !error

  return (
    <>
      {/* Sweep background overlay */}
      <div
        aria-hidden="true"
        style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}
      >
        <div className={`sweep${isLoading ? ' sweep-loading' : ''}`} />
      </div>

      <main className="max-w-2xl mx-auto px-6 py-12" style={{ position: 'relative', zIndex: 1 }}>
        <Link
          to="/"
          className="font-mono transition-colors mb-10 inline-block"
          style={{ fontSize: '11px', color: 'var(--text-muted)', letterSpacing: '0.09em' }}
        >
          ← datasets
        </Link>

        {error && (
          <p className="font-mono text-sm" style={{ color: 'var(--fail-fg)' }}>
            {error}
          </p>
        )}

        {isLoading && (
          <p className="font-mono text-sm" style={{ color: 'var(--text-muted)' }}>
            carregando…
          </p>
        )}

        {report && (
          <>
            <header className="mb-10">
              <div className="flex items-center gap-2.5 mb-2">
                <BrandMark />
                <h1 className="font-sans font-medium" style={{ fontSize: '19px', color: 'var(--text-primary)' }}>
                  {report.dataset_name}
                </h1>
              </div>
              <p
                className="font-mono uppercase"
                style={{ fontSize: '10px', letterSpacing: '0.09em', color: 'var(--text-muted)' }}
              >
                {report.counts.rows !== null && `${report.counts.rows.toLocaleString('pt-BR')} LINHAS · `}
                {`${report.counts.columns} COLUNAS · ${report.counts.findings} FINDINGS · ${report.counts.claims} AFIRMAÇÕES`}
              </p>
            </header>

            <TabNav activeTab={activeTab} onChange={setActiveTab} />

            <div id="panel-summary" role="tabpanel" hidden={activeTab !== 'summary'}>
              {runId && <SummaryPanel runId={runId} />}
            </div>

            <div id="panel-report" role="tabpanel" hidden={activeTab !== 'report'}>
              <ClaimsView
                sections={report.sections}
                metrics={metrics}
                onOpenChain={setSelectedClaimId}
              />
            </div>

            <div id="panel-validation" role="tabpanel" hidden={activeTab !== 'validation'}>
              {runId && <ValidationPanel runId={runId} />}
            </div>
          </>
        )}
      </main>

      <EvidenceDrawer
        claimId={selectedClaimId}
        onClose={() => setSelectedClaimId(null)}
      />
    </>
  )
}
