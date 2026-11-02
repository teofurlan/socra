/**
 * Finds the text of a spoken clip inside the text the page displays, so it can be highlighted.
 *
 * The server sends a clip's source text with its markdown (`**Bold** sentence.`), while the page
 * shows the rendered result (`Bold sentence.`). Both sides are compared on their letters and
 * digits only, which drops the markup and every whitespace difference (line breaks, list
 * markers, spacing between blocks) at once.
 */

export interface TextPosition {
  /** Index into the list of text pieces. */
  node: number
  offset: number
}

export interface SpokenMatch {
  start: TextPosition
  end: TextPosition
  /** Letters and digits up to the end of the match; pass it as ``after`` to find the next clip. */
  consumed: number
}

const SIGNIFICANT = /[\p{L}\p{N}]/u

/**
 * Drops what the page does not show as text: code blocks, link targets and the numbers of
 * ordered list items (the page draws them as list markers, so they are not in its text).
 * The server puts each piece of a clip on its own line, so a list number is at a line start.
 */
function shownMarkdown(source: string): string {
  return source
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/\[([^\]\n]*)\]\([^)\s]*\)/g, '$1')
    .replace(/^[ \t]*\d{1,9}[.)][ \t]+/gm, '')
}

function significant(text: string): string {
  let out = ''
  for (const char of text) if (SIGNIFICANT.test(char)) out += char.toLowerCase()
  return out
}

/**
 * Locates ``spoken`` in the concatenation of ``texts`` (the text nodes of the displayed entry).
 *
 * ``after`` skips that many letters and digits first, so a sentence repeated earlier in the
 * reply is not matched again. Returns null when the text cannot be found.
 */
export function findSpokenText(texts: string[], spoken: string, after = 0): SpokenMatch | null {
  const needle = significant(shownMarkdown(spoken))
  if (!needle) return null

  // One entry per significant character: where it sits in the original pieces.
  const positions: TextPosition[] = []
  let haystack = ''
  texts.forEach((text, node) => {
    let offset = 0
    for (const char of text) {
      if (SIGNIFICANT.test(char)) {
        positions.push({ node, offset })
        haystack += char.toLowerCase()
      }
      offset += char.length
    }
  })

  const index = haystack.indexOf(needle, Math.max(0, after))
  if (index < 0) return null
  const first = positions[index]
  const last = positions[index + needle.length - 1]
  // Include the punctuation glued to the last word (the period of "sentence.").
  const lastText = texts[last.node]
  let endOffset = last.offset + String.fromCodePoint(lastText.codePointAt(last.offset) ?? 0).length
  for (const char of lastText.slice(endOffset)) {
    if (SIGNIFICANT.test(char) || /\s/.test(char)) break
    endOffset += char.length
  }
  return {
    start: first,
    end: { node: last.node, offset: endOffset },
    consumed: index + needle.length,
  }
}

/**
 * The ``scrollTop`` that puts the middle of a range in the middle of the visible scroll area.
 * Rects are viewport coordinates (``getBoundingClientRect``); the result is never negative.
 */
export function centeredScrollTop(
  range: { top: number; height: number },
  scroller: { top: number },
  scrollTop: number,
  clientHeight: number,
): number {
  const middleInView = range.top + range.height / 2 - scroller.top
  return Math.max(0, scrollTop + middleInView - clientHeight / 2)
}
