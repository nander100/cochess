import { useEffect, useMemo, useState } from 'react'
import { type PlaybackDeps, Settler } from '../analysis/playback'
import { positionsAlong } from '../analysis/walkthrough'
import type { LineLink, Playback } from '../api/types'

export interface PlayState {
  link: LineLink
  /** The start and the position after each move. */
  fens: readonly string[]
  /** 0: the start; k: after the line's k-th move. */
  step: number
  playing: boolean
  /** Where to stop and why, once the backend has decided (SPEC_V3 §9.6). */
  settled: Playback | null
  /** "Continue the line": play past the settle point to the end. */
  continued: boolean
  /** At the settle point (or the end): the caption and the stop buttons show. */
  stopped: boolean
}

/** What the board shows during playback. */
export interface PlayView {
  fen: string
  lastMove: string | null // null at the start: the board keeps the start's own move
  winPct: number | null
  evalText: string | null
}

/** Where playback stops now: the settle point, unless the player chose to continue. */
function limit(state: PlayState): number {
  const end = state.link.moves_uci.length
  return state.settled && !state.continued ? Math.min(state.settled.settle_ply, end) : end
}

/** One move later, stopping at the limit. */
function advanced(state: PlayState): PlayState {
  const stop = limit(state)
  const step = Math.min(state.step + 1, stop)
  return step >= stop ? { ...state, step, playing: false, stopped: true } : { ...state, step }
}

/**
 * Line playback (SPEC_V3 §9.5): a linked line plays on the board, one move every `seconds`,
 * and stops where the position has settled. Playback starts at once; the settle point is applied
 * as soon as the backend knows it. The game tree is never touched.
 */
export function usePlayback(deps: PlaybackDeps, seconds: number) {
  const [settler] = useState(() => new Settler(deps))
  const [state, setState] = useState<PlayState | null>(null)

  useEffect(() => {
    if (!state?.playing) return undefined
    const timer = setTimeout(() => setState((s) => (s ? advanced(s) : s)), seconds * 1000)
    return () => clearTimeout(timer)
  }, [state, seconds])

  function play(link: LineLink) {
    const fens = positionsAlong(link.start_path_uci, link.moves_uci)
    setState({ link, fens, step: 0, playing: true, settled: null, continued: false, stopped: false })
    settler.settle(link).then(
      (settled) =>
        setState((s) => {
          if (!s || s.link.line_id !== link.line_id) return s
          const known = { ...s, settled }
          // Already past where it should have stopped: stop here.
          const late = !s.continued && s.step >= settled.settle_ply
          return late ? { ...known, playing: false, stopped: true } : known
        }),
      () => undefined, // no settle point: the whole line plays
    )
  }

  const update = (change: (s: PlayState) => PlayState) => setState((s) => (s ? change(s) : s))

  const view = useMemo((): PlayView | null => {
    if (!state) return null
    const { step, settled, link } = state
    return {
      fen: state.fens[step],
      lastMove: step > 0 ? link.moves_uci[step - 1] : null,
      winPct: settled?.win_pcts[step] ?? null,
      evalText: settled?.evals[step] ?? null,
    }
  }, [state])

  return {
    state,
    view,
    play,
    /** Scan linked lines in the background, so playback stops at the right place at once. */
    prefetch: (links: readonly LineLink[]) => {
      for (const link of links) void settler.settle(link).catch(() => undefined)
    },
    pause: () => update((s) => ({ ...s, playing: false })),
    resume: () => update((s) => (s.step >= limit(s) ? s : { ...s, playing: true, stopped: false })),
    /** Play the rest of the line, past the settle point. */
    continueLine: () =>
      update((s) => ({ ...s, continued: true, stopped: false, playing: s.step < s.link.moves_uci.length })),
    back: () => update((s) => ({ ...s, playing: false, stopped: false, step: Math.max(0, s.step - 1) })),
    forward: () => update((s) => ({ ...advanced({ ...s, continued: true }), playing: false })),
    replay: () => update((s) => ({ ...s, step: 0, playing: true, stopped: false, continued: false })),
    close: () => setState(null),
  }
}

export type PlaybackControls = ReturnType<typeof usePlayback>
