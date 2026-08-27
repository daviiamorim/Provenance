// Mock API server — Node.js built-in http only, no dependencies.
// Runs on port 8000 and mimics the FastAPI backend for frontend development.
// Usage: node web/mock-server.mjs

import { createServer } from 'http'

const DATASET_ID = 'dset-a3f1c2e4b5d6a7f8c9e0b1d2a3f4c5e6'
const RUN_ID = 'run-b8c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7'

const MSR_MISSING_RENDA  = 'msr-11aabbcc11aabbcc11aabbcc11aabbcc'
const MSR_MISSING_IDADE  = 'msr-22aabbcc22aabbcc22aabbcc22aabbcc'
const MSR_MISSING_DEPT   = 'msr-33aabbcc33aabbcc33aabbcc33aabbcc'
const MSR_NORM_RENDA     = 'msr-44aabbcc44aabbcc44aabbcc44aabbcc'
const MSR_NORM_IDADE     = 'msr-55aabbcc55aabbcc55aabbcc55aabbcc'
const MSR_DESC_RENDA     = 'msr-66aabbcc66aabbcc66aabbcc66aabbcc'
const MSR_UNIQ_ID        = 'msr-77aabbcc77aabbcc77aabbcc77aabbcc'
const MSR_FREQ_DEPT      = 'msr-88aabbcc88aabbcc88aabbcc88aabbcc'
const MSR_UNIQ_DEPT      = 'msr-99aabbcc99aabbcc99aabbcc99aabbcc'
const MSR_CORR           = 'msr-aabbcc00aabbcc00aabbcc00aabbcc00'

const FND_MISSING_RENDA  = 'fnd-11ffeedd11ffeedd11ffeedd11ffeedd'
const FND_MISSING_IDADE  = 'fnd-22ffeedd22ffeedd22ffeedd22ffeedd'
const FND_MISSING_DEPT   = 'fnd-33ffeedd33ffeedd33ffeedd33ffeedd'
const FND_SHAPE_RENDA    = 'fnd-44ffeedd44ffeedd44ffeedd44ffeedd'
const FND_SHAPE_IDADE    = 'fnd-55ffeedd55ffeedd55ffeedd55ffeedd'
const FND_DUPLIC         = 'fnd-66ffeedd66ffeedd66ffeedd66ffeedd'
const FND_BALANCE_DEPT   = 'fnd-77ffeedd77ffeedd77ffeedd77ffeedd'
const FND_ASSOC          = 'fnd-88ffeedd88ffeedd88ffeedd88ffeedd'

const AST_MODELING       = 'ast-11ccbbaa11ccbbaa11ccbbaa11ccbbaa'
const AST_QUALITY        = 'ast-22ccbbaa22ccbbaa22ccbbaa22ccbbaa'

const CLM_1 = 'clm-aaaabbbb1111cccc2222dddd3333eeee'
const CLM_2 = 'clm-bbbbcccc2222dddd3333eeee4444ffff'
const CLM_3 = 'clm-ccccdddd3333eeee4444ffff5555aaaa'
const CLM_4 = 'clm-ddddeeee4444ffff5555aaaa6666bbbb'

// ── Mock data ────────────────────────────────────────────────────────────────

const datasets = [
  {
    id: DATASET_ID,
    created_at: '2026-08-20T14:32:00Z',
    manifest: [{ path: 'colaboradores.csv', digest: 'sha256:a1b2c3d4e5f6' }],
  },
]

const runs = [
  {
    id: RUN_ID,
    dataset_id: DATASET_ID,
    producer_versions: { 'plugins.tabular': '0.1.0' },
    config_digest: 'abc123',
    created_at: '2026-08-20T14:33:00Z',
  },
]

const measurements = {
  [MSR_MISSING_RENDA]: {
    id: MSR_MISSING_RENDA,
    dataset_id: DATASET_ID,
    type: 'core.quality.missing',
    scope: { kind: 'column', refs: ['renda_mensal'] },
    payload: { missing_count: 38, row_count: 502, missing_proportion: 0.0757 },
    provenance: {
      producer: 'plugins.tabular._stats.missing_rate',
      version: '0.1.0',
      params: { null_sentinels: ['', 'NA', 'N/A'] },
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 12,
      seed: null,
    },
  },
  [MSR_MISSING_IDADE]: {
    id: MSR_MISSING_IDADE,
    dataset_id: DATASET_ID,
    type: 'core.quality.missing',
    scope: { kind: 'column', refs: ['idade'] },
    payload: { missing_count: 0, row_count: 502, missing_proportion: 0.0 },
    provenance: {
      producer: 'plugins.tabular._stats.missing_rate',
      version: '0.1.0',
      params: { null_sentinels: ['', 'NA', 'N/A'] },
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 9,
      seed: null,
    },
  },
  [MSR_MISSING_DEPT]: {
    id: MSR_MISSING_DEPT,
    dataset_id: DATASET_ID,
    type: 'core.quality.missing',
    scope: { kind: 'column', refs: ['departamento'] },
    payload: { missing_count: 3, row_count: 502, missing_proportion: 0.006 },
    provenance: {
      producer: 'plugins.tabular._stats.missing_rate',
      version: '0.1.0',
      params: { null_sentinels: ['', 'NA', 'N/A'] },
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 8,
      seed: null,
    },
  },
  [MSR_NORM_RENDA]: {
    id: MSR_NORM_RENDA,
    dataset_id: DATASET_ID,
    type: 'core.stats.normality',
    scope: { kind: 'column', refs: ['renda_mensal'] },
    payload: { test: 'shapiro_wilk', statistic: 0.84, p_value: 0.0001, sample_size: 464 },
    provenance: {
      producer: 'plugins.tabular._stats.normality',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 45,
      seed: null,
    },
  },
  [MSR_NORM_IDADE]: {
    id: MSR_NORM_IDADE,
    dataset_id: DATASET_ID,
    type: 'core.stats.normality',
    scope: { kind: 'column', refs: ['idade'] },
    payload: { test: 'shapiro_wilk', statistic: 0.97, p_value: 0.042, sample_size: 502 },
    provenance: {
      producer: 'plugins.tabular._stats.normality',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 38,
      seed: null,
    },
  },
  [MSR_DESC_RENDA]: {
    id: MSR_DESC_RENDA,
    dataset_id: DATASET_ID,
    type: 'core.stats.descriptive',
    scope: { kind: 'column', refs: ['renda_mensal'] },
    payload: { mean: 8420.5, std: 4210.3, min: 1200.0, max: 32000.0, skewness: 1.8, excess_kurtosis: 4.2, sample_size: 464 },
    provenance: {
      producer: 'plugins.tabular._stats.descriptive',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 22,
      seed: null,
    },
  },
  [MSR_UNIQ_ID]: {
    id: MSR_UNIQ_ID,
    dataset_id: DATASET_ID,
    type: 'core.quality.uniqueness',
    scope: { kind: 'dataset', refs: [] },
    payload: { row_count: 502, unique_count: 502, duplicate_count: 0, duplicate_proportion: 0.0 },
    provenance: {
      producer: 'plugins.tabular._stats.uniqueness',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 18,
      seed: null,
    },
  },
  [MSR_FREQ_DEPT]: {
    id: MSR_FREQ_DEPT,
    dataset_id: DATASET_ID,
    type: 'core.stats.frequency',
    scope: { kind: 'column', refs: ['departamento'] },
    payload: {
      categories: ['Vendas', 'TI', 'RH', 'Financeiro', 'Operações'],
      counts: [201, 98, 62, 87, 54],
      proportions: [0.401, 0.195, 0.124, 0.173, 0.107],
      top_proportion: 0.401,
      unique_count: 5,
    },
    provenance: {
      producer: 'plugins.tabular._stats.frequency',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 15,
      seed: null,
    },
  },
  [MSR_UNIQ_DEPT]: {
    id: MSR_UNIQ_DEPT,
    dataset_id: DATASET_ID,
    type: 'core.quality.uniqueness',
    scope: { kind: 'column', refs: ['departamento'] },
    payload: { row_count: 502, unique_count: 5, duplicate_count: 497, duplicate_proportion: 0.99 },
    provenance: {
      producer: 'plugins.tabular._stats.uniqueness',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 11,
      seed: null,
    },
  },
  [MSR_CORR]: {
    id: MSR_CORR,
    dataset_id: DATASET_ID,
    type: 'core.stats.correlation',
    scope: { kind: 'pair', refs: ['renda_mensal', 'idade'] },
    payload: { method: 'pearson', coefficient: 0.61, p_value: 0.000001, sample_size: 464 },
    provenance: {
      producer: 'plugins.tabular._stats.correlation',
      version: '0.1.0',
      params: {},
      input_digest: 'sha256:f1e2d3c4b5a6',
      duration_ms: 28,
      seed: null,
    },
  },
}

const findings = {
  [FND_MISSING_RENDA]: {
    id: FND_MISSING_RENDA,
    dataset_id: DATASET_ID,
    type: 'core.finding.missing_rate',
    scope: { kind: 'column', refs: ['renda_mensal'] },
    statement: 'renda_mensal has 7.6% missing values (38 of 502 rows).',
    severity: 'warn',
    derived_from: [MSR_MISSING_RENDA],
    rule: 'core.finding.missing_rate',
    rule_version: '1.0.0',
    params: { warn_threshold: 0.05, null_sentinels_applied: ['', 'NA', 'N/A'] },
  },
  [FND_MISSING_IDADE]: {
    id: FND_MISSING_IDADE,
    dataset_id: DATASET_ID,
    type: 'core.finding.missing_rate',
    scope: { kind: 'column', refs: ['idade'] },
    statement: 'idade has 0.0% missing values (0 of 502 rows).',
    severity: 'ok',
    derived_from: [MSR_MISSING_IDADE],
    rule: 'core.finding.missing_rate',
    rule_version: '1.0.0',
    params: { warn_threshold: 0.05, null_sentinels_applied: ['', 'NA', 'N/A'] },
  },
  [FND_MISSING_DEPT]: {
    id: FND_MISSING_DEPT,
    dataset_id: DATASET_ID,
    type: 'core.finding.missing_rate',
    scope: { kind: 'column', refs: ['departamento'] },
    statement: 'departamento has 0.6% missing values (3 of 502 rows).',
    severity: 'ok',
    derived_from: [MSR_MISSING_DEPT],
    rule: 'core.finding.missing_rate',
    rule_version: '1.0.0',
    params: { warn_threshold: 0.05, null_sentinels_applied: ['', 'NA', 'N/A'] },
  },
  [FND_SHAPE_RENDA]: {
    id: FND_SHAPE_RENDA,
    dataset_id: DATASET_ID,
    type: 'core.finding.distribution_shape',
    scope: { kind: 'column', refs: ['renda_mensal'] },
    statement: 'renda_mensal shows non-normal distribution (SW=0.84, skewness=1.8). High right skew detected.',
    severity: 'fail',
    derived_from: [MSR_NORM_RENDA, MSR_DESC_RENDA],
    rule: 'core.finding.distribution_shape',
    rule_version: '1.0.0',
    params: { threshold_ok: 0.95, threshold_warn: 0.90, skewness_threshold_ok: 0.50, skewness_threshold_warn: 1.00 },
  },
  [FND_SHAPE_IDADE]: {
    id: FND_SHAPE_IDADE,
    dataset_id: DATASET_ID,
    type: 'core.finding.distribution_shape',
    scope: { kind: 'column', refs: ['idade'] },
    statement: 'idade shows approximately normal distribution (SW=0.97).',
    severity: 'ok',
    derived_from: [MSR_NORM_IDADE],
    rule: 'core.finding.distribution_shape',
    rule_version: '1.0.0',
    params: { threshold_ok: 0.95, threshold_warn: 0.90 },
  },
  [FND_DUPLIC]: {
    id: FND_DUPLIC,
    dataset_id: DATASET_ID,
    type: 'core.finding.duplicate_rate',
    scope: { kind: 'dataset', refs: [] },
    statement: 'Dataset has 0.0% duplicate rows (0 of 502).',
    severity: 'ok',
    derived_from: [MSR_UNIQ_ID],
    rule: 'core.finding.duplicate_rate',
    rule_version: '1.0.0',
    params: { warn_threshold: 0.01 },
  },
  [FND_BALANCE_DEPT]: {
    id: FND_BALANCE_DEPT,
    dataset_id: DATASET_ID,
    type: 'core.finding.category_balance',
    scope: { kind: 'column', refs: ['departamento'] },
    statement: 'departamento top category "Vendas" covers 40.1% of rows. Distribution is acceptable.',
    severity: 'ok',
    derived_from: [MSR_FREQ_DEPT, MSR_UNIQ_DEPT],
    rule: 'core.finding.category_balance',
    rule_version: '1.0.0',
    params: { warn_threshold: 0.60, fail_threshold: 0.80 },
  },
  [FND_ASSOC]: {
    id: FND_ASSOC,
    dataset_id: DATASET_ID,
    type: 'core.finding.variable_association',
    scope: { kind: 'pair', refs: ['renda_mensal', 'idade'] },
    statement: 'renda_mensal and idade show moderate positive correlation (r=0.61).',
    severity: 'warn',
    derived_from: [MSR_CORR],
    rule: 'core.finding.variable_association',
    rule_version: '1.0.0',
    params: { emit_threshold: 0.30, fail_threshold: 0.70 },
  },
}

const assessments = {
  [AST_MODELING]: {
    id: AST_MODELING,
    dataset_id: DATASET_ID,
    type: 'core.assessment.modeling_readiness',
    goal: 'modeling_readiness',
    verdict: 'needs_attention',
    severity: 'warn',
    derived_from: [FND_MISSING_RENDA, FND_SHAPE_RENDA, FND_ASSOC],
    rule: 'core.assessment.modeling_readiness',
    rule_version: '1.0.0',
    policy: { missing_warn_threshold: 0.05, missing_fail_threshold: 0.20 },
  },
  [AST_QUALITY]: {
    id: AST_QUALITY,
    dataset_id: DATASET_ID,
    type: 'core.assessment.data_quality',
    goal: 'data_quality',
    verdict: 'acceptable',
    severity: 'warn',
    derived_from: [FND_MISSING_RENDA, FND_DUPLIC],
    rule: 'core.assessment.data_quality',
    rule_version: '1.0.0',
    policy: { missing_warn_threshold: 0.05, duplicate_warn_threshold: 0.01 },
  },
}

const report = {
  run_id: RUN_ID,
  dataset_id: DATASET_ID,
  dataset_name: 'colaboradores.csv',
  counts: { rows: 502, columns: 8, findings: 8, claims: 4 },
  sections: [
    {
      goal: 'modeling_readiness',
      claims: [
        {
          id: CLM_1,
          text: 'O dataset apresenta atenção necessária para uso em modelagem preditiva. A variável renda_mensal possui 7,6% de valores ausentes, acima do limiar de 5% recomendado para modelos sem imputação explícita.',
          supports: [AST_MODELING, FND_MISSING_RENDA],
          severity: 'warn',
        },
        {
          id: CLM_2,
          text: 'A distribuição de renda_mensal é fortemente assimétrica à direita (W=0,84, assimetria=1,8), o que pode degradar modelos que assumem normalidade dos resíduos. Transformação logarítmica deve ser considerada.',
          supports: [FND_SHAPE_RENDA],
          severity: 'fail',
        },
      ],
    },
    {
      goal: 'data_quality',
      claims: [
        {
          id: CLM_3,
          text: 'A qualidade geral dos dados é aceitável. Não foram detectadas linhas duplicadas. A taxa de ausentes em renda_mensal (7,6%) é o principal ponto de atenção.',
          supports: [AST_QUALITY, FND_DUPLIC, FND_MISSING_RENDA],
          severity: 'warn',
        },
        {
          id: CLM_4,
          text: 'As variáveis renda_mensal e idade apresentam correlação positiva moderada (r=0,61), indicando que trabalhadores mais velhos tendem a ter rendas maiores neste dataset.',
          supports: [FND_ASSOC],
          severity: 'warn',
        },
      ],
    },
  ],
}

const chains = {
  [CLM_1]: {
    root_id: CLM_1,
    claim: {
      id: CLM_1,
      dataset_id: DATASET_ID,
      run_id: RUN_ID,
      text: report.sections[0].claims[0].text,
      supports: [AST_MODELING, FND_MISSING_RENDA],
      validation: {
        status: 'passed',
        attempts: 1,
        checks: [
          { layer: 'syntactic', verdict: 'pass', reason_code: 'ok', detail: {}, duration_ms: 1 },
          { layer: 'numeric', verdict: 'pass', reason_code: 'ok', detail: { numbers_found: ['7,6%'], all_anchored: true }, duration_ms: 3 },
          { layer: 'semantic', verdict: 'pass', reason_code: 'entailed', detail: {}, duration_ms: 210 },
        ],
        final_layer_reached: 'semantic',
      },
    },
    assessments: [assessments[AST_MODELING]],
    findings: [findings[FND_MISSING_RENDA], findings[FND_SHAPE_RENDA], findings[FND_ASSOC]],
    measurements: [measurements[MSR_MISSING_RENDA], measurements[MSR_NORM_RENDA], measurements[MSR_CORR]],
  },
  [CLM_2]: {
    root_id: CLM_2,
    claim: {
      id: CLM_2,
      dataset_id: DATASET_ID,
      run_id: RUN_ID,
      text: report.sections[0].claims[1].text,
      supports: [FND_SHAPE_RENDA],
      validation: {
        status: 'passed',
        attempts: 2,
        checks: [
          { layer: 'syntactic', verdict: 'pass', reason_code: 'ok', detail: {}, duration_ms: 1 },
          { layer: 'numeric', verdict: 'pass', reason_code: 'ok', detail: { numbers_found: ['0,84', '1,8'], all_anchored: true }, duration_ms: 4 },
          { layer: 'semantic', verdict: 'pass', reason_code: 'entailed', detail: {}, duration_ms: 188 },
        ],
        final_layer_reached: 'semantic',
      },
    },
    assessments: [],
    findings: [findings[FND_SHAPE_RENDA]],
    measurements: [measurements[MSR_NORM_RENDA], measurements[MSR_DESC_RENDA]],
  },
  [CLM_3]: {
    root_id: CLM_3,
    claim: {
      id: CLM_3,
      dataset_id: DATASET_ID,
      run_id: RUN_ID,
      text: report.sections[1].claims[0].text,
      supports: [AST_QUALITY, FND_DUPLIC, FND_MISSING_RENDA],
      validation: {
        status: 'passed',
        attempts: 1,
        checks: [
          { layer: 'syntactic', verdict: 'pass', reason_code: 'ok', detail: {}, duration_ms: 1 },
          { layer: 'numeric', verdict: 'pass', reason_code: 'ok', detail: { numbers_found: ['7,6%'], all_anchored: true }, duration_ms: 2 },
          { layer: 'semantic', verdict: 'pass', reason_code: 'entailed', detail: {}, duration_ms: 195 },
        ],
        final_layer_reached: 'semantic',
      },
    },
    assessments: [assessments[AST_QUALITY]],
    findings: [findings[FND_DUPLIC], findings[FND_MISSING_RENDA]],
    measurements: [measurements[MSR_UNIQ_ID], measurements[MSR_MISSING_RENDA]],
  },
  [CLM_4]: {
    root_id: CLM_4,
    claim: {
      id: CLM_4,
      dataset_id: DATASET_ID,
      run_id: RUN_ID,
      text: report.sections[1].claims[1].text,
      supports: [FND_ASSOC],
      validation: {
        status: 'passed',
        attempts: 1,
        checks: [
          { layer: 'syntactic', verdict: 'pass', reason_code: 'ok', detail: {}, duration_ms: 1 },
          { layer: 'numeric', verdict: 'pass', reason_code: 'ok', detail: { numbers_found: ['0,61'], all_anchored: true }, duration_ms: 3 },
          { layer: 'semantic', verdict: 'pass', reason_code: 'entailed', detail: {}, duration_ms: 201 },
        ],
        final_layer_reached: 'semantic',
      },
    },
    assessments: [],
    findings: [findings[FND_ASSOC]],
    measurements: [measurements[MSR_CORR]],
  },
}

const validation = [
  {
    id: 'rej-aaa111bbb222ccc333',
    run_id: RUN_ID,
    text: 'O dataset apresenta excelente qualidade em todas as dimensões analisadas.',
    layer: 'semantic',
    reason_code: 'contradicted',
    detail: { verdict: 'contradicted', cited_ids: [AST_QUALITY] },
    attempt: 1,
  },
  {
    id: 'rej-ddd444eee555fff666',
    run_id: RUN_ID,
    text: 'A variável renda_mensal possui 45,3% de valores ausentes.',
    layer: 'numeric',
    reason_code: 'unanchored_number',
    detail: { number: '45.3', candidates: [0.0757], tolerance: 0.005 },
    attempt: 1,
  },
  {
    id: 'rej-ggg777hhh888iii999',
    run_id: RUN_ID,
    text: 'Os dados apresentam problemas graves de qualidade que inviabilizam qualquer uso.',
    layer: 'syntactic',
    reason_code: 'no_citation',
    detail: { sentences_without_citation: 1 },
    attempt: 2,
  },
]

const metrics = {
  run_id: RUN_ID,
  counts: { measurements: 10, findings: 8, assessments: 2, claims_passed: 4 },
  severity: { ok: 5, warn: 2, fail: 1 },
  total_rejections: 3,
  rejections_syntactic: 1,
  rejections_numeric: 1,
  rejections_semantic: 1,
}

// ── Router ───────────────────────────────────────────────────────────────────

function json(res, data, status = 200) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' })
  res.end(JSON.stringify(data))
}

function notFound(res) {
  json(res, { detail: 'not found' }, 404)
}

const server = createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:8000`)
  const path = url.pathname

  console.log(`${req.method} ${path}`)

  // GET /datasets
  if (path === '/datasets' && req.method === 'GET') return json(res, datasets)

  // GET /datasets/:id/runs
  const runsMatch = path.match(/^\/datasets\/([^/]+)\/runs$/)
  if (runsMatch && req.method === 'GET') {
    return json(res, runsMatch[1] === DATASET_ID ? runs : [])
  }

  // GET /runs/:id/report
  const reportMatch = path.match(/^\/runs\/([^/]+)\/report$/)
  if (reportMatch && req.method === 'GET') {
    return reportMatch[1] === RUN_ID ? json(res, report) : notFound(res)
  }

  // GET /runs/:id/validation
  const validationMatch = path.match(/^\/runs\/([^/]+)\/validation$/)
  if (validationMatch && req.method === 'GET') {
    return validationMatch[1] === RUN_ID ? json(res, validation) : json(res, [])
  }

  // GET /runs/:id/metrics
  const metricsMatch = path.match(/^\/runs\/([^/]+)\/metrics$/)
  if (metricsMatch && req.method === 'GET') {
    return metricsMatch[1] === RUN_ID ? json(res, metrics) : notFound(res)
  }

  // GET /chain/:itemId
  const chainMatch = path.match(/^\/chain\/([^/]+)$/)
  if (chainMatch && req.method === 'GET') {
    const itemId = chainMatch[1]
    const chain = chains[itemId]
    return chain ? json(res, chain) : notFound(res)
  }

  // POST /datasets/upload — mock: consume body and return the existing dataset
  if (path === '/datasets/upload' && req.method === 'POST') {
    let body = ''
    req.on('data', (chunk) => { body += chunk })
    req.on('end', () => {
      console.log(`  → upload recebido (${body.length} bytes)`)
      json(res, datasets[0], 200)
    })
    return
  }

  notFound(res)
})

server.listen(8000, () => {
  console.log('Mock API running on http://localhost:8000')
  console.log('Frontend: http://localhost:5173')
})
