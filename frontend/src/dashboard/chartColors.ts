import { useMemo } from 'react'
import { useTheme } from '../theme/themeContext'

/** The series colors, in the fixed order of the chart palette (tokens --chart-1 to --chart-5). */
export const SERIES = ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5'] as const

/** Design tokens as colors for SVG charts: Recharts takes plain color strings, so the tokens are
 * read from <html>, and read again when the theme changes. Pass a module-level array. */
export function useTokenColors<T extends string>(names: readonly T[]): Record<T, string> {
  const { theme } = useTheme()
  return useMemo(() => {
    void theme // the values depend on the theme
    const style = getComputedStyle(document.documentElement)
    return Object.fromEntries(names.map((name) => [name, style.getPropertyValue(name).trim()])) as Record<T, string>
  }, [theme, names])
}
