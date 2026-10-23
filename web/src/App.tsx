import React, { useCallback, useState } from 'react'
import './App.css'
import { AlertTriangle } from 'lucide-react'
import { useExamSocket } from '@/hooks/useExamSocket'
import { useMicCapture } from '@/hooks/useMicCapture'
import { useAudioInputs } from '@/hooks/useAudioInputs'
import { OrbVisualizer } from '@/components/OrbVisualizer'
import { QuestionPanel } from '@/components/QuestionPanel'
import { SettingsMenu } from '@/components/SettingsMenu'
import { VoicePicker } from '@/components/VoicePicker'
import { PushToTalkControl } from '@/components/PushToTalkControl'
import { CodePane } from '@/components/CodePane'
import { WalkthroughPanel } from '@/components/WalkthroughPanel'
import { Panel } from '@/components/shell/Panel'
import { BackgroundPattern } from '@/components/shell/BackgroundPattern'
import { PromptLine } from '@/components/shell/PromptLine'
import { StateLine } from '@/components/shell/StateLine'
import { Chip, TopBar } from '@/components/shell/TopBar'
import { useTheme } from '@/lib/theme'
import {
  getStoredSilenceTimeout,
  setStoredSilenceTimeout,
  getStoredOrbPalette,
  setStoredOrbPalette,
  getStoredMicDeviceId,
  setStoredMicDeviceId,
  getStoredShape,
  getStoredVisualizer,
  setStoredShape,
  setStoredVisualizer,
} from '@/lib/storage'
import type { ShapeId, VisualizerId } from '@/components/visualizers'

const STATE_LABEL: Record<string, string> = {
  speaking: 'Examiner speaking',
  listening: 'Your turn: speak your answer',
  thinking: 'Examiner thinking',
  idle: 'Ready',
}

export const App: React.FC = () => {
  const { state, setMode, reanswer, sendText, sendAudio, controlWalkthrough, getOutputVolume, listeningEpoch, voices, setVoice } = useExamSocket()

  const [silenceTimeoutMs, setSilenceTimeoutMs] = useState<number>(getStoredSilenceTimeout)
  const [paletteId, setPaletteId] = useState<string>(getStoredOrbPalette)
  const [visualizer, setVisualizer] = useState<VisualizerId>(getStoredVisualizer)
  const [shape, setShape] = useState<ShapeId>(getStoredShape)
  const [micDeviceId, setMicDeviceId] = useState<string>(getStoredMicDeviceId)
  // The code the user closed; new code opens the pane again.
  const [closedCode, setClosedCode] = useState<string | null>(null)
  const { microphones, refresh: refreshMicrophones } = useAudioInputs()
  const { pref: themePref, theme, setPref: setThemePref } = useTheme()

  const handleFinalize = useCallback(
    (base64: string) => {
      sendAudio(base64)
    },
    [sendAudio],
  )

  const { micError, micFallback, getInputVolume, silenceCountdownMs, onTalkingChange } = useMicCapture({
    protocolState: state.protocolState,
    mode: state.mode,
    silenceTimeoutMs,
    listeningEpoch,
    deviceId: micDeviceId,
    onFinalize: handleFinalize,
  })

  const question = state.question
  const walkthrough = state.walkthrough
  const codeKey = walkthrough
    ? `walkthrough:${walkthrough.code}`
    : question?.code !== undefined && !state.finished
      ? `${question.index}:${question.code}`
      : null
  const showCode = codeKey !== null && codeKey !== closedCode
  const walkthroughRunning = !!walkthrough && walkthrough.status !== 'ended'
  const canAnswer = (walkthroughRunning || (!!question && !state.finished)) && state.connectionStatus !== 'disconnected'

  const settings = (
    <SettingsMenu
      mode={state.mode}
      onModeChange={setMode}
      silenceTimeoutMs={silenceTimeoutMs}
      onSilenceChange={(ms) => {
        setSilenceTimeoutMs(ms)
        setStoredSilenceTimeout(ms)
      }}
      paletteId={paletteId}
      onPaletteChange={(id) => {
        setPaletteId(id)
        setStoredOrbPalette(id)
      }}
      visualizer={visualizer}
      onVisualizerChange={(id) => {
        setVisualizer(id)
        setStoredVisualizer(id)
      }}
      shape={shape}
      onShapeChange={(id) => {
        setShape(id)
        setStoredShape(id)
      }}
      microphones={microphones}
      micDeviceId={micDeviceId}
      onMicChange={(id) => {
        setMicDeviceId(id)
        setStoredMicDeviceId(id)
      }}
      micFallback={micFallback}
      onOpen={refreshMicrophones}
      themePref={themePref}
      onThemeChange={setThemePref}
      voicePicker={<VoicePicker voices={voices.voices} current={voices.current} onChange={setVoice} />}
    />
  )

  return (
    <div className="shell">
      <BackgroundPattern />
      <TopBar
        page="exam"
        connection={state.connectionStatus}
        chips={
          walkthrough
            ? <Chip mono>Walkthrough</Chip>
            : question && !state.finished
              ? <Chip mono>{`Question ${question.index}/${question.total}`}</Chip>
              : undefined
        }
        menu={settings}
      />
      <div className="shell-panels" data-split={showCode}>
        <Panel
          className="h-full"
          title={<span>Exam</span>}
        >
          <div className="shell-scroll flex flex-col items-center gap-5">
            <div className="viz-slot w-full max-w-64 shrink-0">
              <OrbVisualizer
                protocolState={state.protocolState}
                getOutputVolume={getOutputVolume}
                getInputVolume={getInputVolume}
                paletteId={paletteId}
                visualizer={visualizer}
                shape={shape}
                questionText={question?.text}
                theme={theme}
              />
            </div>

            <StateLine
              state={state.protocolState}
              label={STATE_LABEL[state.protocolState] ?? STATE_LABEL.idle}
              mode={state.mode}
              countdownMs={silenceCountdownMs}
            />

            {micError && (
              <div
                role="alert"
                data-testid="mic-error-banner"
                className="t-small flex w-full max-w-[72ch] items-start gap-2 [overflow-wrap:anywhere]"
                style={{ color: 'var(--danger)' }}
              >
                <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                <span className="min-w-0 flex-1">{micError}</span>
              </div>
            )}

            {state.notice && (
              <div
                role="status"
                data-testid="notice-banner"
                className="t-small w-full max-w-[72ch] [overflow-wrap:anywhere]"
                style={{ color: 'var(--warn)' }}
              >
                {state.notice}
              </div>
            )}

            {walkthrough ? (
              <WalkthroughPanel walkthrough={walkthrough} onControl={controlWalkthrough} />
            ) : state.finished ? (
              <section role="status" className="w-full max-w-[72ch] py-6 text-center">
                <h2 className="m-0 text-[1.0625rem] font-semibold">Exam finished</h2>
              </section>
            ) : (
              <QuestionPanel
                question={question}
                transcript={state.transcript}
                protocolState={state.protocolState}
                onReanswer={reanswer}
              />
            )}
          </div>

          <PromptLine
            label="Type your answer"
            placeholder={walkthroughRunning ? 'Type repeat, back, next or stop' : canAnswer ? 'Type your answer' : 'Waiting for a question'}
            disabled={!canAnswer}
            onSend={sendText}
            aside={!state.finished && state.mode === 'push-to-talk' ? <PushToTalkControl onTalkingChange={onTalkingChange} /> : undefined}
          />
        </Panel>

        <div className="shell-seam" aria-hidden="true" />
        <div className="code-slot" aria-hidden={!showCode} inert={!showCode}>
          {walkthrough ? (
            <CodePane
              code={walkthrough.code}
              name={walkthrough.language || 'walkthrough'}
              lang={walkthrough.language}
              focus={walkthrough.step?.lines ?? null}
              label="Walkthrough code"
              onClose={() => setClosedCode(codeKey)}
            />
          ) : question?.code !== undefined && (
            <CodePane code={question.code} name={`question ${question.index}`} label="Question code" onClose={() => setClosedCode(codeKey)} />
          )}
        </div>
      </div>

    </div>
  )
}

export default App
