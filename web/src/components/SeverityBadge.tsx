type Severity = 'ok' | 'warn' | 'fail'

interface Props {
  severity: Severity
}

const styles: Record<Severity, string> = {
  fail: 'border border-[var(--color-fail)] text-[var(--color-fail)] bg-[color-mix(in_srgb,var(--color-fail)_12%,transparent)]',
  warn: 'border border-[var(--color-warn)] text-[var(--color-warn)]',
  ok: 'border border-[var(--color-ok)] text-[var(--color-ok)]',
}

const labels: Record<Severity, string> = {
  fail: 'FAIL',
  warn: 'WARN',
  ok: 'OK',
}

export function SeverityBadge({ severity }: Props) {
  return (
    <span
      className={`inline-block font-mono text-[10px] tracking-widest px-1.5 py-0.5 rounded ${styles[severity]}`}
      aria-label={`severidade: ${labels[severity]}`}
    >
      {labels[severity]}
    </span>
  )
}
