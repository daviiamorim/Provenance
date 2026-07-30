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
