import type { HTMLAttributes, ReactNode } from 'react'
import './Card.css'

type Box = HTMLAttributes<HTMLElement> & { as?: 'div' | 'section' | 'article' | 'form'; children: ReactNode }

function join(...names: (string | undefined | false)[]): string {
  return names.filter(Boolean).join(' ')
}

/** Bordered card (14px radius). */
export function Card({ as: Tag = 'div', className, ...rest }: Box) {
  return <Tag className={join('ui-card', className)} {...rest} />
}

/** Dark feature card: coach summary, top tendency, coach feedback. */
export function FeatureCard({ as: Tag = 'div', className, ...rest }: Box) {
  return <Tag className={join('ui-feature-card', className)} {...rest} />
}

/** Tinted panel: upload form, chat panel (16px radius). */
export function TintedPanel({ as: Tag = 'div', className, ...rest }: Box) {
  return <Tag className={join('ui-tinted-panel', className)} {...rest} />
}

/** Small uppercase label above a heading ("YOUR GAMES", "Hint"). */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={join('ui-eyebrow', className)}>{children}</p>
}
