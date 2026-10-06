export type ChronicleReview = {
  title: string
  lines: string[]
  notesPath: string
  notes: Record<string, string>
  selected: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'chronicle-review': { review: ChronicleReview | null }
  }
}
