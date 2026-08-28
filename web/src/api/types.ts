export interface ScopeOut {
  kind: string
  refs: string[]
}

export interface ProvenanceOut {
  producer: string
  version: string
  params: Record<string, unknown>
  input_digest: string
  duration_ms: number
  seed: number | null
}

export interface MeasurementOut {
  id: string
  dataset_id: string
  type: string
  scope: ScopeOut
  payload: Record<string, unknown>
  provenance: ProvenanceOut
}

export interface FindingOut {
  id: string
  dataset_id: string
  type: string
  scope: ScopeOut
  statement: string
  severity: string
  derived_from: string[]
  rule: string
  rule_version: string
  params: Record<string, unknown>
}

export interface AssessmentOut {
  id: string
  dataset_id: string
  type: string
  goal: string
  verdict: string
  severity: string
  derived_from: string[]
  rule: string
  rule_version: string
  policy: Record<string, unknown>
}

export interface EvidenceChain {
  root_id: string
  claim: {
    id: string
    dataset_id: string
    run_id: string
    text: string
    supports: string[]
    validation: {
      status: string
      attempts: number
      checks: { layer: string; verdict: string; reason_code: string; detail: Record<string, unknown>; duration_ms: number }[]
      final_layer_reached: string
    }
  } | null
  assessments: AssessmentOut[]
  findings: FindingOut[]
  measurements: MeasurementOut[]
}

export interface RejectionOut {
  id: string
  run_id: string
  text: string
  layer: 'syntactic' | 'numeric' | 'semantic'
  reason_code: string
  detail: Record<string, unknown>
  attempt: number
}

export interface RunCounts {
  measurements: number
  findings: number
  assessments: number
  claims_passed: number
}

export interface SeverityCounts {
  ok: number
  warn: number
  fail: number
}

export interface RunMetrics {
  run_id: string
  counts: RunCounts
  severity: SeverityCounts
  total_rejections: number
  rejections_syntactic: number
  rejections_numeric: number
  rejections_semantic: number
}

export interface UploadOut {
  dataset_id: string
  candidates: Array<{ plugin_name: string; confidence: number; evidence: string }>
}

export interface RunCreateOut {
  run_id: string
}

export interface DatasetOut {
  id: string
  created_at: string
  manifest: Array<{ path: string; digest: string }>
}

export interface RunOut {
  id: string
  dataset_id: string
  producer_versions: Record<string, string>
  config_digest: string
  created_at: string
}

export interface ClaimSummary {
  id: string
  text: string
  supports: string[]
  severity: 'ok' | 'warn' | 'fail'
}

export interface ReportSection {
  goal: string
  claims: ClaimSummary[]
}

export interface ReportCounts {
  rows: number | null
  columns: number
  findings: number
  claims: number
}

export interface ReportOut {
  run_id: string
  dataset_id: string
  dataset_name: string
  counts: ReportCounts
  sections: ReportSection[]
}
