import { type ReactNode, useCallback, useMemo, useRef, useState } from 'react'
import { IconButton } from './Button'
import { AlertIcon, CloseIcon, InfoIcon } from './icons'
import './Toast.css'
import { TOAST_MS, ToastContext, type ToastTone } from './toastContext'

interface ToastItem {
  id: number
  message: string
  tone: ToastTone
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const next = useRef(1)

  const dismiss = useCallback((id: number) => setItems((all) => all.filter((item) => item.id !== id)), [])

  const show = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = next.current++
      setItems((all) => [...all.filter((item) => item.message !== message), { id, message, tone }])
      setTimeout(() => dismiss(id), TOAST_MS[tone])
    },
    [dismiss],
  )

  const api = useMemo(() => ({ show }), [show])
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="ui-toasts" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={`ui-toast ui-toast-${item.tone}`} role={item.tone === 'error' ? 'alert' : 'status'}>
            {item.tone === 'error' ? <AlertIcon /> : <InfoIcon />}
            <p>{item.message}</p>
            <IconButton label="Dismiss" icon={<CloseIcon size="small" />} onClick={() => dismiss(item.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
