export const DUPLICATE_COLORS: string[] = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#06b6d4', // cyan
  '#a855f7', // purple
  '#ec4899', // pink
]

export const duplicateColorCache = new Map<string, string>()

export function getDuplicateGroupColor(groupId: string): string {
  if (duplicateColorCache.has(groupId)) {
    return duplicateColorCache.get(groupId)!
  }
  const index = duplicateColorCache.size % DUPLICATE_COLORS.length
  const color = DUPLICATE_COLORS[index]
  duplicateColorCache.set(groupId, color)
  return color
}
