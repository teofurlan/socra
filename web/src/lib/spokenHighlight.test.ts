import { describe, expect, it } from 'vitest'
import { centeredScrollTop, findSpokenText } from './spokenHighlight'

describe('findSpokenText', () => {
  it('finds markdown source text in the rendered text, ignoring markup', () => {
    const texts = ['Intro. ', 'Bold', ' sentence.', ' Next one.']
    const match = findSpokenText(texts, '**Bold** sentence.')

    expect(match?.start).toEqual({ node: 1, offset: 0 })
    expect(match?.end).toEqual({ node: 2, offset: ' sentence.'.length })
  })

  it('ignores whitespace and case differences', () => {
    const match = findSpokenText(['First\n\nSecond   part'], 'first second  PART')

    expect(match?.start).toEqual({ node: 0, offset: 0 })
    expect(match?.end.offset).toBe('First\n\nSecond   part'.length)
  })

  it('matches across list items that are separate pieces', () => {
    const match = findSpokenText(['One', 'Two'], '- One\n- Two')

    expect(match?.start).toEqual({ node: 0, offset: 0 })
    expect(match?.end).toEqual({ node: 1, offset: 3 })
  })

  it('uses the link label, not its target, and skips code blocks', () => {
    expect(findSpokenText(['See the docs now.'], 'See [the docs](https://x.dev/a) now.')).not.toBeNull()
    expect(findSpokenText(['Before. After.'], 'Before. ```py\nprint(1)\n``` After.')).not.toBeNull()
  })

  it('starts after the previous clip so a repeated sentence maps to its own place', () => {
    const texts = ['Okay. Something else. Okay.']
    const first = findSpokenText(texts, 'Okay.')
    const second = findSpokenText(texts, 'Okay.', first!.consumed + 'Somethingelse'.length)

    expect(first?.start.offset).toBe(0)
    expect(second?.start.offset).toBe('Okay. Something else. '.length)
  })

  it('includes the punctuation that follows the last word, but not the next word', () => {
    const match = findSpokenText(['Done (really)! Next.'], 'Done (really)')

    expect(match?.end.offset).toBe('Done (really)!'.length)
  })

  it('returns null when the text is absent or has nothing to match', () => {
    expect(findSpokenText(['Hello there.'], 'Goodbye.')).toBeNull()
    expect(findSpokenText(['Hello there.'], '**  **')).toBeNull()
    expect(findSpokenText([], 'Hello')).toBeNull()
  })

  it('finds numbered list items, whose numbers the page draws as list markers', () => {
    // User: "no se esté bugeando con los subtítulos que están en negrita"
    const texts = ['Two ideas:', 'One-command setup.', ' The README asks a lot.', 'Barge-in.', ' Voice tools feel natural.']
    expect(findSpokenText(texts, '1. **One-command setup.**')).not.toBeNull()
    expect(findSpokenText(texts, '1) **One-command setup.**\nThe README asks a lot.')).not.toBeNull()
    const grouped = findSpokenText(texts, 'The README asks a lot.\n2. **Barge-in.**\nVoice tools feel natural.')
    expect(grouped).not.toBeNull()
    expect(grouped!.start).toEqual({ node: 2, offset: 1 })
    expect(grouped!.end).toEqual({ node: 4, offset: texts[4].length })
  })

  it('keeps numbers that are part of a sentence', () => {
    const texts = ['It took 3 tries, then 2. Done.']
    expect(findSpokenText(texts, 'It took 3 tries, then 2. Done.')).not.toBeNull()
  })

  it('handles accented letters', () => {
    expect(findSpokenText(['¿Qué es esto? Es útil.'], 'Es **útil**.')?.start.offset).toBe('¿Qué es esto? '.length)
  })
})

describe('centeredScrollTop', () => {
  it('scrolls so the middle of the range sits in the middle of the scroller', () => {
    // Range middle is 310px below the scroller top; the wanted middle is 200px.
    expect(centeredScrollTop({ top: 400, height: 20 }, { top: 100 }, 50, 400)).toBe(160)
  })

  it('scrolls back up when the range is above the middle, and never below zero', () => {
    expect(centeredScrollTop({ top: 110, height: 20 }, { top: 100 }, 300, 400)).toBe(120)
    expect(centeredScrollTop({ top: 100, height: 20 }, { top: 100 }, 10, 400)).toBe(0)
  })
})
