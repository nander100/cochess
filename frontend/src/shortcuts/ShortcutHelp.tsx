import { Modal } from '../ui'
import './ShortcutHelp.css'
import { SHORTCUTS } from './shortcuts'

/** The list of shortcuts: in the help dialog (?) and in Settings. */
export function ShortcutList() {
  return (
    <dl className="shortcut-list">
      {SHORTCUTS.map((shortcut) => (
        <div key={shortcut.id} className="shortcut-row">
          <dt>
            {shortcut.keys.map((key, i) => (
              <span key={key}>
                {i > 0 && <span className="shortcut-or"> or </span>}
                <kbd>{key}</kbd>
              </span>
            ))}
          </dt>
          <dd>{shortcut.label}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ShortcutHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal title="Keyboard shortcuts" open={open} onClose={onClose}>
      <p className="shortcut-note">Shortcuts work whenever you're not typing in a box.</p>
      <ShortcutList />
    </Modal>
  )
}
