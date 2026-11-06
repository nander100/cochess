import { useMemo, useRef, useState } from 'react'
import { type WalkthroughDeps, type WalkthroughProgress, positionsAlong, walkThrough } from '../analysis/walkthrough'
import { type ApiClient, isLoggedOut } from '../api/client'
import type { LiveEngine } from '../board/EnginePanel'
import type { Annotation, Walkthrough } from '../api/types'
import { pathTo } from '../board/tree'
import { errorText } from '../pages/util'

export interface WalkState {
  /** The node the line starts from (UCI path joined by spaces). */
  startId: string
  line: readonly string[]
  progress: WalkthroughProgress | null
  result: Walkthrough | null
  error: string | null
  /** 0: the intro, on the start position; 1..n: after each move of the line. */
  step: number
  saved: boolean
}

/** What the board shows while walking: the step's position, its move, shapes and eval. */
export interface WalkView {
  fen: string
  /** The step's move; null at the intro (the board keeps the start position's own move). */
  lastMove: string | null
  annotations: readonly Annotation[]
  winPct: number | null
  evalText: string | null
}

const NONE: readonly Annotation[] = []

/** A line walkthrough (SPEC_V3 §7.3): opening it fetches (or builds) the walkthrough; the steps
 * are then stepped through on the board. The game tree is untouched unless the line is saved. */
export function useWalkthrough(
  api: ApiClient,
  loadEngine: () => Promise<LiveEngine>,
  gameId: string,
  onLoggedOut: () => void,
) {
  const [walk, setWalk] = useState<WalkState | null>(null)
  const deps: WalkthroughDeps = {
    api,
    async search(fen) {
      const { engine, config } = await loadEngine()
      return engine.analyze({ fen, ply: null }, 'verify', config.verify)
    },
  }
  // Each request has a number, so a late answer to one that was closed or replaced is ignored.
  const latest = useRef(0)

  async function open(startId: string, line: readonly string[]) {
    const request = ++latest.current
    const update = (change: (state: WalkState) => WalkState) =>
      setWalk((state) => (state && request === latest.current ? change(state) : state))
    setWalk({ startId, line, progress: null, result: null, error: null, step: 0, saved: false })
    try {
      const result = await walkThrough(deps, gameId, pathTo(startId), line, (progress) =>
        update((state) => ({ ...state, progress })),
      )
      update((state) => ({ ...state, result, progress: null }))
    } catch (error) {
      if (isLoggedOut(error)) onLoggedOut()
      else update((state) => ({ ...state, error: errorText(error), progress: null }))
    }
  }

  function close() {
    latest.current += 1
    setWalk(null)
  }

  function go(step: number) {
    setWalk((state) => {
      if (!state?.result) return state
      return { ...state, step: Math.max(0, Math.min(step, state.result.steps.length)) }
    })
  }

  const view = useMemo((): WalkView | null => {
    if (!walk) return null
    if (!walk.result || walk.step === 0) {
      const fen = walk.result?.start_fen ?? positionsAlong(pathTo(walk.startId), [])[0]
      return { fen, lastMove: null, annotations: NONE, winPct: null, evalText: null }
    }
    const step = walk.result.steps[walk.step - 1]
    return {
      fen: step.fen_after,
      lastMove: step.uci,
      annotations: step.annotation ? [step.annotation] : NONE,
      winPct: step.win_pct_after,
      evalText: step.eval_after,
    }
  }, [walk])

  return {
    walk,
    view,
    open: (startId: string, line: readonly string[]) => void open(startId, line),
    retry: () => walk && void open(walk.startId, walk.line),
    close,
    go,
    prev: () => walk && go(walk.step - 1),
    next: () => walk && go(walk.step + 1),
    markSaved: () => setWalk((state) => (state ? { ...state, saved: true } : state)),
  }
}

export type WalkthroughControls = ReturnType<typeof useWalkthrough>
