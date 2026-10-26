interface ProgressBarProps {
  label: string
  done: number
  total: number
}

export function ProgressBar({ label, done, total }: ProgressBarProps) {
  return (
    <div className="progress" role="status">
      <p>{label}</p>
      <progress value={done} max={Math.max(total, 1)} aria-label={label} />
    </div>
  )
}
