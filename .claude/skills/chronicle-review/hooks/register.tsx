import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { ChronicleReview } from '../types'

const PANE = 'chronicle-review'
const TOOL = 'mcp__chronicle-review__review'
const HOTKEYS = '123456789abcdefghijklmnopqrstuvwxyz'

const review = atom({ plugin: 'chronicle-review', key: 'review' } as const, null)

type Verdict = 'approve' | 'notes' | 'stop'
type Outcome = {
  verdict: Verdict | null
  notes: { line: number; quote: string; note: string }[]
}

// What the publisher is typing into the note box, kept here so a redraw of
// the pane (any state write) draws the box with the same text instead of
// the saved note. Module-local: a reload of this module loses it, and the
// mod is not edited while a review is open.
let draft = ''
let draftFor: number | null = null

function outcomeOf(state: ChronicleReview, verdict: Verdict | null): Outcome {
  const notes = Object.entries(state.notes)
    .map(([k, note]) => ({ line: Number(k), quote: state.lines[Number(k) - 1] ?? '', note }))
    .sort((a, b) => a.line - b.line)
  return { verdict, notes }
}

// Notes already on disk for this review, so that opening the pane again
// (a second call, a resumed run) never loses what the publisher wrote.
async function savedNotes($: EngineInterface, notesPath: string): Promise<Record<string, string>> {
  const notes: Record<string, string> = {}
  if (!(await $.fs.exists(notesPath))) return notes
  try {
    const parsed = JSON.parse(await $.fs.read(notesPath)) as Partial<Outcome>
    for (const n of parsed.notes ?? []) {
      if (typeof n.line === 'number' && typeof n.note === 'string' && n.note !== '') {
        notes[String(n.line)] = n.note
      }
    }
  } catch {
    // An unreadable file is treated as empty; the next save rewrites it.
  }
  return notes
}

// The publisher's press: write the record, clear the pane's state, and send
// the verdict back as a prompt so the skill's turn resumes.
async function finish($: EngineInterface, verdict: Verdict): Promise<void> {
  const state = await read($, review)
  if (!state) return
  const outcome = outcomeOf(state, verdict)
  await $.fs.write(state.notesPath, JSON.stringify(outcome, null, 2) + '\n')
  await update($, review, () => null)
  draft = ''
  draftFor = null
  const count = outcome.notes.length
  void $.prompt.submit({
    text:
      `Review of "${state.title}": verdict ${verdict}` +
      (verdict === 'notes' ? ` with ${count} note${count === 1 ? '' : 's'}` : '') +
      `. Notes file: ${state.notesPath}`,
  })
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.tool.register({
      name: 'review',
      description:
        'Open a pane showing numbered lines for the publisher to annotate. Returns at once. ' +
        'When the publisher presses Approve, Send back or Stop, the plugin writes ' +
        '{verdict, notes:[{line, quote, note}]} to notes_path and sends a prompt naming the ' +
        'verdict and that path. After calling this, end the turn and wait for that prompt. ' +
        'Notes already in notes_path are kept, so calling it again is safe.',
      inputSchema: {
        type: 'object',
        properties: {
          title: { type: 'string', description: 'The pane title, e.g. "Plan 1: session 28"' },
          lines: { type: 'array', items: { type: 'string' }, description: 'The lines to show, in order' },
          notes_path: { type: 'string', description: 'Where to write the notes JSON' },
        },
        required: ['title', 'lines', 'notes_path'],
      },
    })
    return next(e)
  })

  // A hook has a 10s budget, so the tool opens the pane and returns. The
  // publisher's press comes back as a prompt from this plugin, and the notes
  // file on disk is the record either way.
  on('tool.call', { tool: TOOL }, async ($, e) => {
    const title = String(e.title ?? 'Review')
    const lines = Array.isArray(e.lines) ? e.lines.map(String) : []
    const notesPath = String(e.notes_path ?? '')
    if (lines.length === 0 || notesPath === '') {
      return { deny: 'chronicle-review: lines and notes_path are required.' }
    }
    const current = await read($, review)
    const notes = {
      ...(await savedNotes($, notesPath)),
      ...(current && current.notesPath === notesPath ? current.notes : {}),
    }
    const state: ChronicleReview = { title, lines, notesPath, notes, selected: null }
    await update($, review, () => state)
    await $.fs.write(notesPath, JSON.stringify(outcomeOf(state, null), null, 2) + '\n')
    const opened = await $.ui.open({ id: PANE, title, focus: true })
    if (!opened.isPlaced) {
      $.ui.toast(`chronicle-review: ${opened.reason ?? 'widen the terminal to see the pane'}`)
    }
    const kept = Object.keys(notes).length
    // A plugin tool's result is text for the model.
    return {
      result:
        `Pane "${title}" ${opened.isPlaced ? 'opened' : 'waiting for room'} with ${lines.length} lines` +
        (kept ? ` and ${kept} saved note${kept === 1 ? '' : 's'} kept` : '') +
        `. End the turn. The verdict arrives as a prompt from the chronicle-review plugin, ` +
        `and the notes file is ${notesPath}.`,
    }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'chronicle-review: the pane could not be opened.' },
  )

  on('ui.close', { id: PANE }, async ($, e, next) => {
    if (e.origin.kind === 'person') {
      await finish($, 'stop')
    }
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const table = $.ui.resolve(e)
    const { Box, Text, Button } = table
    // mobile draws no Input: there the pane shows lines and verdicts only.
    const Input = 'Input' in table ? table.Input : null
    const state = await read($, review)
    if (!state) {
      return <Text dimColor>Nothing under review.</Text>
    }

    const save = async (next: ChronicleReview) => {
      await update($, review, () => next)
      await $.fs.write(next.notesPath, JSON.stringify(outcomeOf(next, null), null, 2) + '\n')
    }

    const press = async (verdict: Verdict) => {
      await finish($, verdict)
      await $.ui.close({ id: PANE })
    }

    const count = Object.keys(state.notes).length
    const selected = state.selected
    const boxValue =
      selected !== null && draftFor === selected ? draft : (state.notes[String(selected)] ?? '')

    return (
      <Box flexDirection="column">
        <Text bold>{state.title}</Text>
        <Text dimColor>
          Press a line's key to note it. Enter saves the note, an empty note clears it. Esc returns to the prompt.
        </Text>
        <Text> </Text>
        {state.lines.map((line, i) => {
          const n = i + 1
          const hotkey = HOTKEYS[i]
          const note = state.notes[String(n)]
          const isSelected = selected === n
          return (
            <Box flexDirection="column">
              <Box>
                <Button
                  key={`line:${n}`}
                  plain
                  hotkey={hotkey}
                  label={hotkey ? 'note' : `${n}: note`}
                  dimColor={!isSelected}
                  onPress={() => {
                    draft = state.notes[String(n)] ?? ''
                    draftFor = n
                    void update($, review, s => (s ? { ...s, selected: n } : s))
                  }}
                />
                <Text> </Text>
                <Text inverse={isSelected} wrap="wrap">{line}</Text>
              </Box>
              {note !== undefined && (
                <Box>
                  <Text>    </Text>
                  <Text color="warning" wrap="wrap">{'↳ ' + note}</Text>
                </Box>
              )}
            </Box>
          )
        })}
        <Text> </Text>
        {selected !== null && Input && (
          <Input
            key="note"
            autoFocus
            label={`Note on line ${selected}:`}
            value={boxValue}
            placeholder="what is wrong with it"
            submitLabel="save"
            onInput={(value: string) => {
              draft = value
              draftFor = selected
            }}
            onSubmit={(value: string) => {
              const n = String(selected)
              const notes = { ...state.notes }
              if (value.trim() === '') delete notes[n]
              else notes[n] = value.trim()
              draft = ''
              draftFor = null
              void save({ ...state, notes, selected: null })
            }}
          />
        )}
        <Box>
          <Button key="approve" variant="primary" label="Approve" onPress={() => void press('approve')} />
          <Text> </Text>
          <Button key="send-back" label={count ? `Send back (${count} notes)` : 'Send back'} onPress={() => void press('notes')} />
          <Text> </Text>
          <Button key="stop" label="Stop" onPress={() => void press('stop')} />
        </Box>
      </Box>
    )
  })
}
