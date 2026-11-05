import type { ReactNode, TableHTMLAttributes } from 'react'
import './Table.css'

/** A table in a bordered, 14px-radius box that scrolls sideways when it must; tinted header row. */
export function Table({ className, children, ...rest }: TableHTMLAttributes<HTMLTableElement> & { children: ReactNode }) {
  return (
    <div className="ui-table-box">
      <table className={['ui-table', className ?? ''].join(' ').trim()} {...rest}>
        {children}
      </table>
    </div>
  )
}
