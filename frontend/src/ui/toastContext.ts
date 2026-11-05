import { createContext, useContext } from 'react'

export type ToastTone = 'error' | 'info'

export interface ToastApi {
  /** Show a plain-language message (backend errors arrive here, SPEC_V3 §4.2). */
  show: (message: string, tone?: ToastTone) => void
}

/** How long a toast stays, unless dismissed sooner. Errors stay longer. */
export const TOAST_MS: Record<ToastTone, number> = { info: 5000, error: 9000 }

export const ToastContext = createContext<ToastApi>({ show: () => {} })

export function useToast(): ToastApi {
  return useContext(ToastContext)
}
