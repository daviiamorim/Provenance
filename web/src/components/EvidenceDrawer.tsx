import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { AssessmentOut, EvidenceChain, FindingOut, MeasurementOut } from '../api/types'
import { SeverityBadge } from './SeverityBadge'

interface Props {
  claimId: string | null
  onClose: () => void
}

export function EvidenceDrawer({ claimId, onClose }: Props) {
  const [chain, setChain] = useState<EvidenceChain | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const open = claimId !== null

  useEffect(() => {
    if (!claimId) {
      triggerRef.current?.focus()
      triggerRef.current = null
      setChain(null)
      setError(null)
      return
    }
    triggerRef.current = document.activeElement as HTMLElement
    setLoading(true)
    setError(null)
    api
      .getChain(claimId)
      .then((data) => {
        setChain(data)
        setLoading(false)
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      })
  }, [claimId])

  useEffect(() => {
    if (open && !loading) {
      closeRef.current?.focus()
    }
  }, [open, loading])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40"
          aria-hidden="true"
          onClick={onClose}
        />
      )}

      <div
        role="dialog"
        aria-modal="true"
        aria-label="Cadeia de evidências"
        className={`fixed top-0 right-0 z-50 h-screen w-full md:w-[480px] bg-[var(--color-raised)] border-l border-[var(--color-divider)] flex flex-col transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="shrink-0 flex items-center justify-between px-5 py-4 border-b border-[var(--color-divider)] bg-[var(--color-raised)]">
          <span className="font-mono text-[10px] text-[var(--color-muted)] uppercase tracking-widest">
            cadeia de evidências
          </span>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Fechar painel"
            className="font-mono text-xl text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors w-8 h-8 flex items-center justify-center rounded"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading && (
            <p className="font-mono text-sm text-[var(--color-muted)]">carregando…</p>
          )}
          {error && (
            <p className="font-mono text-sm text-[var(--color-fail)]">{error}</p>
          )}
          {chain && !loading && <ChainTree chain={chain} />}
        </div>
      </div>
    </>
  )
}

// ─── tree ────────────────────────────────────────────────────────────────────

interface FindingWithMeasurements {
  finding: FindingOut
  measurements: MeasurementOut[]
}

interface AssessmentWithChildren {
  assessment: AssessmentOut
  findings: FindingWithMeasurements[]
}

function ChainTree({ chain }: { chain: EvidenceChain }) {
  if (!chain.claim) {
    return (
      <p className="font-mono text-sm text-[var(--color-muted)]">
        cadeia sem claim raiz
      </p>
    )
  }

  const { claim } = chain
  const assessmentMap = new Map(chain.assessments.map((a) => [a.id, a]))
  const findingMap = new Map(chain.findings.map((f) => [f.id, f]))
  const measurementMap = new Map(chain.measurements.map((m) => [m.id, m]))

  const astIds = claim.supports.filter((s) => s.startsWith('ast-'))
  const directFndIds = claim.supports.filter((s) => s.startsWith('fnd-'))

  const fndUnderAst = new Set<string>()

  const assessments: AssessmentWithChildren[] = astIds.flatMap((astId) => {
    const a = assessmentMap.get(astId)
    if (!a) return []
    const findings: FindingWithMeasurements[] = a.derived_from.flatMap((fndId) => {
      fndUnderAst.add(fndId)
      const f = findingMap.get(fndId)
      if (!f) return []
      const measurements = f.derived_from.flatMap((msrId) => {
        const m = measurementMap.get(msrId)
        return m ? [m] : []
      })
      return [{ finding: f, measurements }]
    })
    return [{ assessment: a, findings }]
  })

  const directFindings: FindingWithMeasurements[] = directFndIds.flatMap((fndId) => {
    if (fndUnderAst.has(fndId)) return []
    const f = findingMap.get(fndId)
    if (!f) return []
    const measurements = f.derived_from.flatMap((msrId) => {
      const m = measurementMap.get(msrId)
      return m ? [m] : []
    })
    return [{ finding: f, measurements }]
  })

  return (
    <div className="space-y-6">
      {/* Claim */}
      <div>
        <LayerChip layer="claim" />
        <p className="font-mono text-[10px] text-[var(--color-muted)] mt-1 mb-2 break-all">
          {claim.id}
        </p>
        <p className="font-serif text-[18px] leading-[1.55] text-[var(--color-text)]">
          {claim.text}
        </p>
      </div>

      {/* Assessments */}
      {assessments.map(({ assessment, findings }) => (
        <AssessmentNode key={assessment.id} assessment={assessment} findings={findings} />
      ))}

      {/* Direct findings (not under any assessment) */}
      {directFindings.map(({ finding, measurements }) => (
        <FindingNode key={finding.id} finding={finding} measurements={measurements} />
      ))}
    </div>
  )
}

function AssessmentNode({ assessment, findings }: AssessmentWithChildren) {
  return (
    <div className="pl-4 border-l-2 border-[var(--color-accent)] space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <LayerChip layer="assessment" />
          <SeverityBadge severity={assessment.severity as 'ok' | 'warn' | 'fail'} />
        </div>
        <p className="font-mono text-[10px] text-[var(--color-muted)] mb-2 break-all">
          {assessment.id}
        </p>
        <div className="font-mono text-xs space-y-1 mb-2">
          <KVRow label="goal" value={assessment.goal} />
          <KVRow label="verdict" value={assessment.verdict} />
          <KVRow label="regra" value={`${assessment.rule} · ${assessment.rule_version}`} />
        </div>
        {Object.keys(assessment.policy).length > 0 && (
          <div>
            <span className="font-mono text-[10px] text-[var(--color-muted)] uppercase tracking-wider">
              política
            </span>
            <div className="mt-1">
              <KVPairs data={assessment.policy} />
            </div>
          </div>
        )}
      </div>

      {findings.map(({ finding, measurements }) => (
        <FindingNode key={finding.id} finding={finding} measurements={measurements} />
      ))}
    </div>
  )
}

function FindingNode({ finding, measurements }: FindingWithMeasurements) {
  return (
    <div className="pl-4 border-l-2 border-[var(--color-muted)] space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <LayerChip layer="finding" />
          <SeverityBadge severity={finding.severity as 'ok' | 'warn' | 'fail'} />
        </div>
        <p className="font-mono text-[10px] text-[var(--color-muted)] mb-2 break-all">
          {finding.id}
        </p>
        <p className="font-mono text-sm text-[var(--color-text)] mb-2">{finding.statement}</p>
        <p className="font-mono text-[11px] text-[var(--color-muted)] mb-2">
          {finding.rule} · {finding.rule_version}
        </p>
        {Object.keys(finding.params).length > 0 && <KVPairs data={finding.params} />}
      </div>

      {measurements.map((m) => (
        <MeasurementNode key={m.id} measurement={m} />
      ))}
    </div>
  )
}

function MeasurementNode({ measurement: m }: { measurement: MeasurementOut }) {
  const prov = m.provenance
  return (
    <div className="pl-4 border-l-2 border-[var(--color-divider)] space-y-3">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <LayerChip layer="measurement" />
        </div>
        <p className="font-mono text-[10px] text-[var(--color-muted)] mb-2 break-all">{m.id}</p>
        <p className="font-mono text-xs text-[var(--color-text)] mb-1">{m.type}</p>
        <p className="font-mono text-[11px] text-[var(--color-muted)] mb-3">
          {m.scope.kind} · {m.scope.refs.join(', ')}
        </p>
        {Object.keys(m.payload).length > 0 && <KVPairs data={m.payload} />}

        <div className="mt-3 border border-[var(--color-divider)] rounded px-3 pt-2 pb-3 space-y-1.5">
          <p className="font-mono text-[10px] text-[var(--color-muted)] uppercase tracking-widest mb-2">
            procedência
          </p>
          <ProvLine label="produtor" value={prov.producer} />
          <ProvLine label="versão" value={prov.version} />
          <ProvLine label="duração" value={`${prov.duration_ms}ms`} />
          {Object.keys(prov.params).length > 0 && (
            <ProvLine label="params" value={JSON.stringify(prov.params)} />
          )}
          {prov.seed !== null && <ProvLine label="seed" value={String(prov.seed)} />}
          <div className="flex flex-col gap-0.5 pt-0.5">
            <span className="font-mono text-[10px] text-[var(--color-muted)]">input_digest</span>
            <span className="font-mono text-[11px] text-[var(--color-text)] break-all">
              {prov.input_digest}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── small helpers ────────────────────────────────────────────────────────────

type Layer = 'claim' | 'assessment' | 'finding' | 'measurement'

const layerLabel: Record<Layer, string> = {
  claim: 'CLAIM',
  assessment: 'ASSESSMENT',
  finding: 'FINDING',
  measurement: 'MEASUREMENT',
}

const layerColor: Record<Layer, string> = {
  claim: 'text-[var(--color-text)]',
  assessment: 'text-[var(--color-accent)]',
  finding: 'text-[var(--color-muted)]',
  measurement: 'text-[var(--color-muted)]',
}

function LayerChip({ layer }: { layer: Layer }) {
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-widest ${layerColor[layer]}`}
    >
      {layerLabel[layer]}
    </span>
  )
}

function KVRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 items-baseline">
      <span className="text-[var(--color-muted)] shrink-0">{label}</span>
      <span className="text-[var(--color-text)]">{value}</span>
    </div>
  )
}

function ProvLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 items-baseline">
      <span className="font-mono text-[10px] text-[var(--color-muted)] shrink-0">{label}</span>
      <span className="font-mono text-[11px] text-[var(--color-text)]">{value}</span>
    </div>
  )
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'sim' : 'não'
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return v.toLocaleString('pt-BR')
    return Number(v.toPrecision(4)).toString()
  }
  if (Array.isArray(v)) {
    if (v.length === 0) return '[]'
    return v.map((item) => (typeof item === 'string' ? `"${item}"` : formatValue(item))).join(', ')
  }
  return String(v)
}

function KVPairs({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return null
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-baseline gap-1.5">
          <span className="font-mono text-[10px] text-[var(--color-muted)]">{k}</span>
          <span className="font-mono text-[11px] text-[var(--color-text)]">{formatValue(v)}</span>
        </div>
      ))}
    </div>
  )
}
