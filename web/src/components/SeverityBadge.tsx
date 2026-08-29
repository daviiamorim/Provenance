type Severity = 'ok' | 'warn' | 'fail'

interface Props {
  severity: Severity
}

const styles: Record<Severity, React.CSSProperties> = {
  fail: { background: 'var(--fail-bg)', color: 'var(--fail-fg)' },
  warn: { background: 'var(--warn-bg)', color: 'var(--warn-fg)' },
  ok:   { background: 'var(--ok-bg)',   color: 'var(--ok-fg)'   },
}

const labels: Record<Severity, string> = {
  fail: 'FALHA',
  warn: 'ATENÇÃO',
  ok:   'OK',
}

export function SeverityBadge({ severity }: Props) {
  return (
    <span
      className="inline-block font-sans font-normal rounded shrink-0"
      style={{
        fontSize: '10px',
        letterSpacing: '0.09em',
        padding: '2px 6px',
        textTransform: 'uppercase',
        ...styles[severity],
      }}
      aria-label={`severidade: ${labels[severity]}`}
    >
      {labels[severity]}
    </span>
  )
}
