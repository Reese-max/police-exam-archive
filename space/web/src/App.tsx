import {
  AuiConfig,
  AssistantRuntimeProvider,
  Suggestions,
  useLocalRuntime,
  type ChatModelAdapter,
  type ThreadMessage,
} from '@assistant-ui/react'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  Thread,
  type ThreadComponents,
} from '@/components/assistant-ui/elements/thread.aui'
import { streamChat } from './gradio'

const suggestionTexts = [
  '警察何時可以查證身分？',
  '警察職權行使法第 6 條規定什麼？',
  '考古題中的答案和現行法條不同時應如何判斷？',
  // The backend adds ?essay=1 to the iframe src when essay answers are enabled.
  ...(new URLSearchParams(window.location.search).has('essay')
    ? ['申論題：試述警察查證身分之要件及程序。']
    : []),
]

const getText = (message: ThreadMessage) =>
  message.content
    .filter((part) => part.type === 'text')
    .map((part) => part.text)
    .join('')

const adapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    let questionIndex = -1
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'user') {
        questionIndex = index
        break
      }
    }

    const question =
      questionIndex < 0 ? '' : getText(messages[questionIndex])
    const history = messages.flatMap((message, index) => {
      if (
        index === questionIndex ||
        (message.role !== 'user' && message.role !== 'assistant')
      ) {
        return []
      }
      return [{ role: message.role, content: getText(message) }]
    })

    for await (const reply of streamChat(question, history, abortSignal)) {
      yield {
        content: [
          { type: 'text', text: reply.text },
          ...(reply.sources
            ? [{ type: 'reasoning' as const, text: reply.sources.content }]
            : []),
        ],
      }
    }
  },
}

const config = AuiConfig({ suggestions: Suggestions(suggestionTexts) })

const Welcome = () => (
  <div className="aui-thread-welcome-root mb-6 flex flex-col px-2">
    <p className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl font-medium tracking-tight duration-200">
      警察考古題 AI 助理
    </p>
    <p className="mt-2 text-sm text-muted-foreground">
      AI 回答僅供參考，請以考選部公告與現行條文為準。
    </p>
  </div>
)

const SourcesGroup: NonNullable<ThreadComponents['ReasoningGroup']> = ({
  children,
}) => (
  <details className="my-2 rounded-lg border px-3 py-2 text-sm">
    <summary className="cursor-pointer font-medium">本輪參考來源</summary>
    <div className="mt-3">{children}</div>
  </details>
)

const threadComponents: ThreadComponents = {
  Welcome,
  ReasoningGroup: SourcesGroup,
}

function App() {
  const runtime = useLocalRuntime(adapter)

  return (
    <AssistantRuntimeProvider runtime={runtime} config={config}>
      <TooltipProvider>
        <div className="h-dvh">
          <Thread components={threadComponents} />
        </div>
      </TooltipProvider>
    </AssistantRuntimeProvider>
  )
}

export default App
