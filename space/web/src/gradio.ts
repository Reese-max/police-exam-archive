export type ReplySources = { title: string; content: string } | null

export type GradioReply = {
  text: string
  sources: ReplySources
}

export type GradioMessage = {
  role: 'user' | 'assistant'
  content: string
  metadata?: { title?: string }
}

type StreamEvent = { event: string; data: string }

export function splitReply(messages: GradioMessage[]): GradioReply {
  let lastUserIndex = -1
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') {
      lastUserIndex = index
      break
    }
  }

  const replies = messages
    .slice(lastUserIndex + 1)
    .filter((message) => message.role === 'assistant')
  const sources = replies.findLast((message) => message.metadata?.title)

  return {
    text: replies
      .filter((message) => !message.metadata?.title)
      .map((message) => message.content)
      .join('\n\n'),
    sources: sources
      ? { title: sources.metadata!.title!, content: sources.content }
      : null,
  }
}

const getApiRoot = () => {
  if (import.meta.env?.DEV) {
    return import.meta.env.VITE_GRADIO_URL || 'http://127.0.0.1:7860'
  }
  return location.href.split('/gradio_api/')[0]
}

const errorMessage = (reason?: string) =>
  `伺服器暫時無法回應，請稍後再試。${reason ? `（原因：${reason}）` : ''}`

const readReason = (value: unknown): string | undefined => {
  if (typeof value === 'string') return value || undefined
  if (value && typeof value === 'object') {
    const detail = value as { error?: unknown; message?: unknown }
    if (typeof detail.error === 'string') return detail.error
    if (typeof detail.message === 'string') return detail.message
    return JSON.stringify(value)
  }
  return undefined
}

const parseEvent = (frame: string): StreamEvent => {
  const lines = frame.split(/\r?\n/)
  const event = lines
    .find((line) => line.startsWith('event:'))
    ?.slice('event:'.length)
    .trim()
  const data = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).replace(/^ /, ''))
    .join('\n')
  return { event: event || 'message', data }
}

async function* responseEvents(
  response: Response,
): AsyncGenerator<StreamEvent> {
  if (!response.body) throw new Error(errorMessage())
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let boundary: RegExpExecArray | null
    while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
      const frame = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary[0].length)
      if (frame.trim()) yield parseEvent(frame)
    }
    if (done) break
  }
  if (buffer.trim()) yield parseEvent(buffer)
}

export async function* streamChat(
  question: string,
  history: GradioMessage[],
  signal: AbortSignal,
): AsyncGenerator<GradioReply> {
  const root = getApiRoot()
  let response: Response
  try {
    response = await fetch(`${root}/gradio_api/call/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: [question, history] }),
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new Error(errorMessage(readReason(error)))
  }
  if (!response.ok) {
    let reason: string | undefined
    try {
      const body = await response.text()
      try {
        reason = readReason(JSON.parse(body)) ?? body
      } catch {
        reason = body
      }
    } catch {
      reason = undefined
    }
    throw new Error(errorMessage(reason))
  }

  let eventId: string
  try {
    const body = (await response.json()) as { event_id?: string }
    if (!body.event_id) throw new Error('回應中缺少事件識別碼')
    eventId = body.event_id
  } catch (error) {
    if (signal.aborted) throw error
    throw new Error(errorMessage(readReason(error)))
  }

  let eventsResponse: Response
  try {
    eventsResponse = await fetch(
      `${root}/gradio_api/call/chat/${encodeURIComponent(eventId)}`,
      { signal },
    )
  } catch (error) {
    if (signal.aborted) throw error
    throw new Error(errorMessage(readReason(error)))
  }
  if (!eventsResponse.ok) {
    throw new Error(errorMessage(await eventsResponse.text()))
  }

  try {
    for await (const event of responseEvents(eventsResponse)) {
      if (event.event === 'heartbeat') continue
      if (event.event === 'error') {
        let reason: string | undefined
        try {
          reason = readReason(JSON.parse(event.data))
        } catch {
          reason = event.data || undefined
        }
        throw new Error(errorMessage(reason))
      }
      if (event.event !== 'generating' && event.event !== 'complete') continue
      const payload = JSON.parse(event.data) as [GradioMessage[]]
      yield splitReply(payload[0] ?? [])
    }
  } catch (error) {
    if (signal.aborted) throw error
    if (error instanceof Error && error.message.startsWith('伺服器暫時無法回應')) {
      throw error
    }
    throw new Error(errorMessage(readReason(error)))
  }
}

// Sources block format (space/app.py): a line "[題n]", "[條n]", "[網n]", or "[判n]" starts an item; "## " starts a new section.
export function parseSources(markdown: string): Record<string, string> {
  const items: Record<string, string> = {}
  let key = ''
  for (const line of markdown.split('\n')) {
    const marker = /^\[([題條網判]\d+)\]$/.exec(line.trim())
    if (marker) {
      key = marker[1]
      items[key] = ''
    } else if (line.startsWith('## ')) key = ''
    else if (key) items[key] += `${line}\n`
  }
  return items
}

// Also fixes citations such as "[網1](A)", which markdown would otherwise read as a link to "A".
// shortcut: also rewrites citations inside code spans, switch to a remark plugin if answers start containing code.
export const linkCitations = (text: string) =>
  text.replace(/\[([題條網判]\d+)\]/g, '[$1](#src-$1)')

// "題1"/"條2"/"網3"/"判4" for links made by linkCitations, "" otherwise; decodeURIComponent throws on a bad "%".
export function citationId(href = ''): string {
  try {
    return /^#src-([題條網判]\d+)$/.exec(decodeURIComponent(href))?.[1] ?? ''
  } catch {
    return ''
  }
}
