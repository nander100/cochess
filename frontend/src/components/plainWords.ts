/** Coach text with its `cc:` placeholders as their own words (move words, link text; board
 * icons dropped), for places that show it as plain text, like a one-line teaser. */
export function plainWords(text: string): string {
  return text.replace(/\[([^\]]*)\]\(cc:(board|move|line)\/\d+\)/g, (_, words: string, kind: string) =>
    kind === 'board' ? '' : words,
  )
}
