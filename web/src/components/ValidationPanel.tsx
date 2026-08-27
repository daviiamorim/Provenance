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

const LAYER_EXPLAIN: Record<string, string> = {
  syntactic: 'A frase não contém nenhuma citação rastreável. Toda afirmação precisa referenciar explicitamente um dado verificado.',
  numeric: 'Um número na frase não corresponde a nenhum valor nos dados de origem, nem mesmo com arredondamento.',
  semantic: 'Um segundo modelo de IA leu a frase e as evidências citadas e concluiu que a frase contradiz ou extrapola o que os dados mostram.',
}

const REASON_LABEL: Record<string, string> = {
  no_citation: 'sem citação de fonte',
  unanchored_number: 'número sem lastro nos dados',
  contradicted: 'contradiz as evidências',
  unsupported: 'não suportada pelas evidências',
}

const DETAIL_KEY_LABEL: Record<string, string> = {
  number: 'número encontrado',
  candidates: 'valores possíveis nos dados',
  tolerance: 'tolerância de arredondamento',
  verdict: 'veredito do verificador',
  cited_ids: 'fontes citadas na frase',
  sentences_without_citation: 'frases sem citação',
  all_anchored: 'todos os números têm fonte',
  numbers_found: 'números encontrados',
}

function RejectionCard({ r }: { r: RejectionOut }) {
  const [expanded, setExpanded] = useState(false)
  const layerLabel = LAYER_LABEL[r.layer] ?? r.layer.toUpperCase()
  const layerColor = LAYER_COLOR[r.layer] ?? 'var(--color-muted)'
  const layerExplain = LAYER_EXPLAIN[r.layer] ?? ''
  const reasonLabel = REASON_LABEL[r.reason_code] ?? r.reason_code

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
          {reasonLabel}
        </span>
        <span
          className="ml-auto font-mono text-[10px]"
          style={{ color: 'var(--color-muted)' }}
        >
          tentativa {r.attempt}
        </span>
      </div>

      <p
        className="font-serif text-[15px] leading-[1.5] italic mb-3"
        style={{ color: 'var(--color-muted)' }}
      >
        {r.text}
      </p>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="font-mono text-[10px] uppercase tracking-wider mb-2 flex items-center gap-1.5 transition-colors"
        style={{ color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        aria-expanded={expanded}
      >
        <span style={{ display: 'inline-block', transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }}>▶</span>
        {expanded ? 'ocultar detalhes' : 'por que foi rejeitada?'}
      </button>

      {expanded && (
        <div className="space-y-3">
          {layerExplain && (
            <p
              className="font-mono text-[11px] leading-relaxed"
              style={{ color: 'var(--color-muted)' }}
            >
              {layerExplain}
            </p>
          )}

          {detailEntries.length > 0 && (
            <div
              className="font-mono text-[11px] rounded px-3 py-2 space-y-1"
              style={{
                background: 'color-mix(in srgb, var(--color-fail) 8%, transparent)',
                color: 'var(--color-muted)',
              }}
            >
              {detailEntries.map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="shrink-0" style={{ color: 'var(--color-text)' }}>
                    {DETAIL_KEY_LABEL[k] ?? k}
                  </span>
                  <span className="break-all">{String(Array.isArray(v) ? v.join(', ') : v)}</span>
                </div>
              ))}
            </div>
          )}
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
