import type { DatasetOut, EvidenceChain, RejectionOut, ReportOut, RunCreateOut, RunMetrics, RunOut, UploadOut } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: FormData | Record<string, unknown>): Promise<T> {
  const isForm = body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: isForm ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : JSON.stringify(body),
  })
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
  getValidation: (runId: string) => get<RejectionOut[]>(`/runs/${runId}/validation`),
  getMetrics: (runId: string) => get<RunMetrics>(`/runs/${runId}/metrics`),
  uploadDataset: (file: File) => {
    const form = new FormData()
    form.append('files', file)
    return post<UploadOut>('/datasets/upload', form)
  },
  createRun: (datasetId: string) =>
    post<RunCreateOut>('/runs', {
      dataset_id: datasetId,
      plugin_name: 'tabular',
      goals: ['data_quality', 'modeling_readiness'],
    }),
}
