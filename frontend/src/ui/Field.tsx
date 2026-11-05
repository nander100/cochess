import { type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes, useId } from 'react'
import './Field.css'

interface FieldShellProps {
  id: string
  label: ReactNode
  help?: ReactNode
  error?: string | null
  children: ReactNode
}

/** Label above, help or error below, wired with aria-describedby. */
function FieldShell({ id, label, help, error, children }: FieldShellProps) {
  return (
    <div className="ui-field">
      <label className="ui-field-label" htmlFor={id}>
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-msg`} className="ui-field-error" role="alert">
          {error}
        </p>
      ) : help ? (
        <p id={`${id}-msg`} className="ui-field-help">
          {help}
        </p>
      ) : null}
    </div>
  )
}

type Shared = { label: ReactNode; help?: ReactNode; error?: string | null }

export function Input({ label, help, error, id, className, ...rest }: Shared & InputHTMLAttributes<HTMLInputElement>) {
  const auto = useId()
  const inputId = id ?? auto
  return (
    <FieldShell id={inputId} label={label} help={help} error={error}>
      <input
        id={inputId}
        className={['ui-input', className ?? ''].join(' ').trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={help || error ? `${inputId}-msg` : undefined}
        {...rest}
      />
    </FieldShell>
  )
}

export function Textarea({
  label,
  help,
  error,
  id,
  mono = false,
  className,
  ...rest
}: Shared & { mono?: boolean } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const auto = useId()
  const inputId = id ?? auto
  return (
    <FieldShell id={inputId} label={label} help={help} error={error}>
      <textarea
        id={inputId}
        className={['ui-input', 'ui-textarea', mono ? 'ui-mono' : '', className ?? ''].join(' ').trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={help || error ? `${inputId}-msg` : undefined}
        {...rest}
      />
    </FieldShell>
  )
}

export function Select({ label, help, error, id, className, children, ...rest }: Shared & SelectHTMLAttributes<HTMLSelectElement>) {
  const auto = useId()
  const inputId = id ?? auto
  return (
    <FieldShell id={inputId} label={label} help={help} error={error}>
      <select
        id={inputId}
        className={['ui-input', 'ui-select', className ?? ''].join(' ').trim()}
        aria-invalid={error ? true : undefined}
        aria-describedby={help || error ? `${inputId}-msg` : undefined}
        {...rest}
      >
        {children}
      </select>
    </FieldShell>
  )
}
