interface Props {
  theme: 'dark' | 'light'
  onToggle: () => void
}

export function ThemeToggle({ theme, onToggle }: Props) {
  return (
    <button
      onClick={onToggle}
      aria-label={theme === 'dark' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
      className="text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors text-sm font-mono"
    >
      {theme === 'dark' ? '☀' : '☾'}
    </button>
  )
}
