import type { DatasetOut, EvidenceChain, ReportOut, RunOut } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listDatasets: () => get<DatasetOut[]>('/datasets'),
  listRuns: (datasetId: string) => get<RunOut[]>(`/datasets/${datasetId}/runs`),
  getReport: (runId: string) => get<ReportOut>(`/runs/${runId}/report`),
  getChain: (itemId: string) => get<EvidenceChain>(`/chain/${itemId}`),
}
