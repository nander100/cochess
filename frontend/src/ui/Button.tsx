import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Button.css'
import './icons.css'

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'danger' | 'link'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  children: ReactNode
}

/** Buttons from the design: primary (navy / baby blue), secondary (black / white), outline, plus
 * danger for destructive confirms and link for inline text actions. 44px tall. Disabled keeps its
 * shape at lower contrast. */
export function Button({ variant = 'primary', className, type = 'button', disabled, ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      className={['ui-button', `ui-button-${variant}`, className ?? ''].join(' ').trim()}
      {...rest}
    />
  )
}

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'children'> {
  /** Required: the button has no visible text (SPEC_V3 §4.5). */
  label: string
  icon: ReactNode
  variant?: 'outline' | 'primary' | 'header'
}

export function IconButton({ label, icon, variant = 'outline', className, type = 'button', disabled, ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      className={['ui-icon-button', `ui-icon-button-${variant}`, className ?? ''].join(' ').trim()}
      {...rest}
    >
      {icon}
    </button>
  )
}
