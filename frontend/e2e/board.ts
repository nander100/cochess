import type { Page } from '@playwright/test'

/** Click a square on the chessground board, seen from `orientation`'s side. */
export async function clickSquare(page: Page, square: string, orientation: 'white' | 'black'): Promise<void> {
  const box = await page.locator('cg-board').boundingBox()
  if (!box) throw new Error('No board on the page.')
  const size = box.width / 8
  let file = square.charCodeAt(0) - 'a'.charCodeAt(0)
  let rank = Number(square[1]) - 1
  if (orientation === 'black') {
    file = 7 - file
    rank = 7 - rank
  }
  await page.mouse.click(box.x + (file + 0.5) * size, box.y + (7 - rank + 0.5) * size)
}

/** Play a move (UCI) on the board by clicking its squares. */
export async function playMove(page: Page, uci: string, orientation: 'white' | 'black'): Promise<void> {
  await clickSquare(page, uci.slice(0, 2), orientation)
  await clickSquare(page, uci.slice(2, 4), orientation)
}
