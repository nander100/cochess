import { Button, ChevronLeftIcon, ChevronRightIcon, IconButton, PauseIcon, PlayIcon, ReplayIcon } from '../ui'
import type { PlaybackControls, PlayState } from './usePlayback'
import './PlaybackBar.css'

interface PlaybackBarProps {
  playback: PlaybackControls
  state: PlayState
  /** Open the line's walkthrough (SPEC_V3 §7). */
  onWalk: () => void
  onSave: () => void
  saved: boolean
}

/** The control bar under the board during line playback (SPEC_V3 §9.5). At the settle point it
 * shows the caption, built by the backend from the boards, and what to do next. */
export function PlaybackBar({ playback, state, onWalk, onSave, saved }: PlaybackBarProps) {
  const total = state.link.moves_uci.length
  return (
    <section className="playback" aria-label="Line playback">
      <p className="playback-title">
        <strong>{state.link.label}</strong>
        <span className="playback-count">
          Move {state.step} of {total}
        </span>
      </p>
      {state.stopped && (
        <p className="playback-caption" role="status">
          {state.settled?.caption ?? 'That is the end of the line.'}
        </p>
      )}
      <div className="playback-controls">
        <IconButton
          label="Step back"
          icon={<ChevronLeftIcon size="small" />}
          onClick={playback.back}
          disabled={state.step === 0}
        />
        {state.playing ? (
          <IconButton label="Pause" icon={<PauseIcon size="small" />} onClick={playback.pause} />
        ) : (
          <IconButton label="Play" icon={<PlayIcon size="small" />} onClick={playback.resume} disabled={state.stopped} />
        )}
        <IconButton
          label="Step forward"
          icon={<ChevronRightIcon size="small" />}
          onClick={playback.forward}
          disabled={state.step === total}
        />
        <IconButton label="Replay" icon={<ReplayIcon size="small" />} onClick={playback.replay} />
        <Button variant="outline" onClick={playback.close}>
          Back to position
        </Button>
      </div>
      {state.stopped && (
        <div className="playback-next">
          {state.step < total && <Button onClick={playback.continueLine}>Continue the line</Button>}
          <Button variant="secondary" onClick={onWalk}>
            Walk me through it
          </Button>
          <Button variant="outline" onClick={onSave} disabled={saved}>
            {saved ? 'Saved as a variation' : 'Save as variation'}
          </Button>
        </div>
      )}
    </section>
  )
}
