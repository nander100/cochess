import type { ReactNode, SVGProps } from 'react'

/** Inline stroke icons in the design's style (docs/design/tokens.md "Controls"): 24-unit viewBox,
 * 2px round strokes, `currentColor`. Decorative: the control that holds one carries the label. */
type IconProps = Omit<SVGProps<SVGSVGElement>, 'children'> & { size?: 'small' | 'normal' }

function Icon({ size = 'normal', className, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={['ui-icon', size === 'small' ? 'ui-icon-small' : '', className ?? ''].join(' ').trim()}
      {...rest}
    >
      {children}
    </svg>
  )
}

export const SunIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
)
export const MoonIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icon>
)
export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12l5 5 9-10" />
  </Icon>
)
export const ChevronLeftIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15 18l-6-6 6-6" />
  </Icon>
)
export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 18l6-6-6-6" />
  </Icon>
)
export const FirstIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M17 18l-6-6 6-6M7 6v12" />
  </Icon>
)
export const LastIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 18l6-6-6-6M17 6v12" />
  </Icon>
)
export const FlipIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 4v16M7 4l-3 3M7 4l3 3M17 20V4M17 20l-3-3M17 20l3-3" />
  </Icon>
)
export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
)
export const AlertIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5M12 16.5v.5" />
  </Icon>
)
export const InfoIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.5" />
  </Icon>
)
export const KeyboardIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" />
  </Icon>
)
