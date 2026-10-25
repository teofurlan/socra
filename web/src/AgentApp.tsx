import React, { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { AlertTriangle } from 'lucide-react'
import { useAgentSocket } from '@/hooks/useAgentSocket'
import { useMicCapture } from '@/hooks/useMicCapture'
import { useAudioInputs } from '@/hooks/useAudioInputs'
import { OrbVisualizer } from '@/components/OrbVisualizer'
import { SettingsMenu } from '@/components/SettingsMenu'
import { VoicePicker } from '@/components/VoicePicker'
import { PushToTalkControl } from '@/components/PushToTalkControl'
import { AgentComposerControls } from '@/components/AgentComposerControls'
import { AgentTimeline } from '@/components/AgentTimeline'
import { PermissionPromptCard } from '@/components/PermissionPromptCard'
import { ModeSwitchCard } from '@/components/ModeSwitchCard'
import { CodePane } from '@/components/CodePane'
import { Panel } from '@/components/shell/Panel'
import { BackgroundPattern } from '@/components/shell/BackgroundPattern'
import { PromptLine } from '@/components/shell/PromptLine'
import { StateLine } from '@/components/shell/StateLine'
import { Chip, TopBar } from '@/components/shell/TopBar'
import { useTheme } from '@/lib/theme'
import { chooseSelection } from '@/lib/agentSelection'
import { splitCode } from '@/lib/codeBlocks'
import {
  getStoredAgentFolder,
  getStoredAgentSelection,
  getStoredMicDeviceId,
  getStoredOrbPalette,
  getStoredSilenceTimeout,
  getStoredTurnMode,
  getStoredShape,
  getStoredVisualizer,
  setStoredAgentFolder,
  setStoredAgentSelection,
  setStoredMicDeviceId,
  setStoredOrbPalette,
  setStoredSilenceTimeout,
  setStoredTurnMode,
  setStoredShape,
  setStoredVisualizer,
} from '@/lib/storage'
import type { ShapeId, VisualizerId } from '@/components/visualizers'
import type { ProtocolState, TurnMode } from '@/types/exam'
import type { AgentMode, AgentSelection } from '@/types/agent'

const STATE_LABEL: Record<string, string> = {
  speaking: 'Agent speaking',
  listening: 'Your turn: say what to do',
  thinking: 'Agent working',
  idle: 'Ready',
}

const folderName = (path: string) => path.split(/[\\/]/).filter(Boolean).at(-1) ?? path
const folderKey = (path: string) => path.replace(/[\\/]+$/, '').replaceAll('\\', '/')

export const AgentApp: React.FC = () => {
  const socket = useAgentSocket()
  const { state, dispatch } = socket

  const [storedSelection, setStoredSelection] = useState<AgentSelection | null>(getStoredAgentSelection)
  const [startNotice, setStartNotice] = useState<string | null>(null)
  // The mode the next session starts in; once a session runs, the selector switches instead.
  const [startMode, setStartMode] = useState<AgentMode>('agent')
  const pendingStartRef = useRef<{ selection: AgentSelection; cwd: string } | null>(null)
  const folderPickerBaselineRef = useRef<{ cwd: string | null } | null>(null)
  const [mode, setMode] = useState<TurnMode>(() => getStoredTurnMode('auto'))
  const [silenceTimeoutMs, setSilenceTimeoutMs] = useState<number>(getStoredSilenceTimeout)
  const [paletteId, setPaletteId] = useState<string>(getStoredOrbPalette)
  // Shared with the exam page: one preference for the whole app.
  const [visualizer, setVisualizer] = useState<VisualizerId>(getStoredVisualizer)
  const [shape, setShape] = useState<ShapeId>(getStoredShape)
  const [micDeviceId, setMicDeviceId] = useState<string>(getStoredMicDeviceId)
  // The timeline entry whose code the user closed; newer code opens the pane again.
  const [closedCodeId, setClosedCodeId] = useState<number | null>(null)
  const { microphones, refresh: refreshMicrophones } = useAudioInputs()
  const { pref: themePref, theme, setPref: setThemePref } = useTheme()

  const selection = chooseSelection(state.backends, storedSelection, state.defaultSelection)
  const connected = state.connectionStatus === 'connected'
  const busy = state.protocolState === 'thinking' || state.protocolState === 'speaking'
  const selectedBackend = state.backends.find((backend) => backend.id === selection?.backend)
  const inputReady = connected && !!selection && selectedBackend?.status.state === 'ready' && !!state.folder
  const inputProtocolState: ProtocolState = state.protocolState === 'idle' || state.protocolState === 'listening'
    ? inputReady ? 'listening' : 'idle'
    : state.protocolState
  const visualizerProtocolState: ProtocolState = state.session ? inputProtocolState : 'idle'

  // Restore the last folder once; later picks and starts come from the server.
  useEffect(() => {
    const folder = getStoredAgentFolder()
    if (folder) dispatch({ type: 'set_folder', path: folder })
  }, [dispatch])

  useEffect(() => {
    if (state.folder) setStoredAgentFolder(state.folder)
  }, [state.folder])

  useEffect(() => {
    const baseline = folderPickerBaselineRef.current
    if (!state.pickingFolder && baseline) {
      if (baseline.cwd && state.folder && folderKey(baseline.cwd) !== folderKey(state.folder)) {
        const pending = pendingStartRef.current
        const pendingUsesOldFolder = pending && folderKey(pending.cwd) !== folderKey(state.folder)
        const sessionUsesOldFolder = state.session && folderKey(state.session.cwd) !== folderKey(state.folder)
        if (pendingUsesOldFolder || sessionUsesOldFolder) {
          socket.interrupt()
          pendingStartRef.current = null
        }
      }
      folderPickerBaselineRef.current = null
    }
  }, [socket.interrupt, state.folder, state.pickingFolder, state.session])

  useEffect(() => {
    const pending = pendingStartRef.current
    if (!pending) return
    const accepted = state.session?.backend === pending.selection.backend &&
      state.session.model === pending.selection.model && folderKey(state.session.cwd) === folderKey(pending.cwd)
    if (accepted || state.timeline.at(-1)?.kind === 'error') pendingStartRef.current = null
  }, [state.session, state.timeline])

  const ensureSessionStarted = (next: AgentSelection, cwd: string) => {
    const sessionMatches = state.session?.backend === next.backend && state.session.model === next.model && folderKey(state.session.cwd) === folderKey(cwd)
    const pending = pendingStartRef.current
    const pendingMatches = pending?.selection.backend === next.backend && pending.selection.model === next.model && folderKey(pending.cwd) === folderKey(cwd)
    if (!sessionMatches && !pendingMatches) {
      pendingStartRef.current = { selection: next, cwd }
      const supportsModes = state.backends.find((backend) => backend.id === next.backend)?.supports_modes === true
      socket.start(next, cwd, supportsModes && startMode !== 'agent' ? startMode : undefined)
    }
  }

  const handleSendAudio = (audio: string) => {
    const backend = state.backends.find((candidate) => candidate.id === selection?.backend)
    if (!selection || !backend || backend.status.state !== 'ready') {
      setStartNotice('Choose a ready agent and model before speaking.')
      return
    }
    if (!state.folder) {
      setStartNotice('Choose a folder before speaking.')
      return
    }
    ensureSessionStarted(selection, state.folder)
    setStartNotice(null)
    socket.sendAudio(audio)
  }

  const { micError, micFallback, getInputVolume, silenceCountdownMs, onTalkingChange } = useMicCapture({
    protocolState: inputProtocolState,
    mode,
    silenceTimeoutMs,
    listeningEpoch: socket.listeningEpoch,
    deviceId: micDeviceId,
    onFinalize: handleSendAudio,
  })

  const handleSelectionChange = (next: AgentSelection) => {
    const pending = pendingStartRef.current
    const pendingSelectionChanges = pending && (pending.selection.backend !== next.backend || pending.selection.model !== next.model)
    const sessionSelectionChanges = state.session && (state.session.backend !== next.backend || state.session.model !== next.model)
    if (pendingSelectionChanges || sessionSelectionChanges) {
      socket.interrupt()
      pendingStartRef.current = null
    }
    setStoredSelection(next)
    setStoredAgentSelection(next)
  }

  const handlePickFolder = () => {
    folderPickerBaselineRef.current = { cwd: state.folder }
    socket.pickFolder()
  }

  const handleSendText = (text: string) => {
    const backend = state.backends.find((candidate) => candidate.id === selection?.backend)
    if (!selection || !backend || backend.status.state !== 'ready') {
      setStartNotice('Choose a ready agent and model before sending. Your message is still here.')
      return false
    }
    if (!state.folder) {
      setStartNotice('Choose a folder before sending. Your message is still here.')
      return false
    }
    ensureSessionStarted(selection, state.folder)
    setStartNotice(null)
    socket.sendText(text)
  }

  const handleModeChange = (next: TurnMode) => {
    setMode(next)
    setStoredTurnMode(next)
  }

  const session = state.session
  const sessionBackend = state.backends.find((backend) => backend.id === session?.backend)
  const sessionModel = sessionBackend?.models.find((model) => model.id === session?.model)
  // Before a session the selector picks the starting mode; during one it switches with a
  // handoff. Either way only a backend that supports modes offers them.
  const modeBackend = session ? sessionBackend : state.backends.find((backend) => backend.id === selection?.backend)
  const modesSupported = modeBackend?.supports_modes === true
  const modeControl = {
    mode: session?.mode ?? (modesSupported ? startMode : 'agent'),
    onChange: session ? socket.switchMode : setStartMode,
    disabled: !modesSupported,
    reason: modeBackend && !modesSupported ? 'Mode switching needs Claude Code' : undefined,
    switching: state.switching,
  } as const
  const lastEntry = state.timeline.at(-1)
  const setupError = lastEntry?.kind === 'error' ? lastEntry.text : null
  // The letter looks spell the latest reply, or the latest turn before any reply.
  const lettersText = [...state.timeline].reverse().find((entry) => entry.kind === 'reply' || entry.kind === 'user')?.text

  // The newest reply that carries code feeds the code pane.
  const code = useMemo(() => {
    for (let i = state.timeline.length - 1; i >= 0; i--) {
      const entry = state.timeline[i]
      if (entry.kind !== 'reply' && entry.kind !== 'text') continue
      const { blocks } = splitCode(entry.text)
      if (blocks.length > 0) {
        return { id: entry.id, name: blocks[0].lang || 'code', lang: blocks[0].lang, text: blocks.map((b) => b.code).join('\n\n') }
      }
    }
    return null
  }, [state.timeline])
  const showCode = code !== null && code.id !== closedCodeId

  const settings = (
    <SettingsMenu
      mode={mode}
      onModeChange={handleModeChange}
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
      voicePicker={<VoicePicker voices={socket.voices.voices} current={socket.voices.current} onChange={socket.setVoice} />}
    />
  )

  return (
    <div className="shell">
      <BackgroundPattern />
      <TopBar
        page="agent"
        connection={state.connectionStatus}
        chips={
          session ? (
            <>
              <Chip>{`${sessionModel?.label ?? session.model} · ${sessionBackend?.label ?? session.backend}`}</Chip>
              <Chip mono title={session.cwd}>
                {folderName(session.cwd)}
              </Chip>
            </>
          ) : undefined
        }
        menu={settings}
      />
      <div className="shell-panels" data-split={showCode}>
        <Panel
          className="h-full"
          title={<span>Conversation</span>}
          meta={
            session ? (
              <span data-testid="session-bar" className="flex min-w-0 items-center gap-2">
                {/* The top bar's chips carry the model and folder from tablet width up. */}
                <span className="t-small truncate md:hidden" style={{ color: 'var(--label-2)' }}>
                  {sessionModel?.label ?? session.model}
                  <span className="hidden sm:inline"> · {sessionBackend?.label ?? session.backend}</span>
                </span>
                <span className="t-mono truncate md:hidden" title={session.cwd} style={{ color: 'var(--label)' }}>
                  {folderName(session.cwd)}
                </span>
              </span>
            ) : undefined
          }
          label="Conversation"
        >
          <div className="voice-stage flex shrink-0 flex-col items-center">
            <div className="viz-slot w-full shrink-0 max-w-64">
              <OrbVisualizer
                protocolState={visualizerProtocolState}
                getOutputVolume={socket.getOutputVolume}
                getInputVolume={getInputVolume}
                paletteId={paletteId}
                visualizer={visualizer}
                shape={shape}
                questionText={lettersText}
                theme={theme}
              />
            </div>

            <StateLine
              state={inputProtocolState}
              label={STATE_LABEL[inputProtocolState] ?? STATE_LABEL.idle}
              mode={mode}
              countdownMs={silenceCountdownMs}
            />
          </div>

          <div className="shell-scroll flex flex-col items-center gap-5">
            {(micError || setupError) && (
              <div
                role="alert"
                className="t-small flex w-full max-w-[72ch] items-start gap-2 [overflow-wrap:anywhere]"
                style={{ color: 'var(--danger)' }}
              >
                <AlertTriangle aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                <span className="min-w-0 flex-1">{micError ?? setupError}</span>
              </div>
            )}

            {startNotice && <div role="status" className="t-small w-full max-w-[72ch] [overflow-wrap:anywhere]" style={{ color: 'var(--warn)' }}>{startNotice}</div>}

            {state.notice && (
              <div role="status" className="t-small w-full max-w-[72ch] [overflow-wrap:anywhere]" style={{ color: 'var(--warn)' }}>
                {state.notice}
              </div>
            )}

            <div className="flex w-full max-w-[80ch] flex-1 flex-col">
              <AgentTimeline entries={state.timeline} protocolState={state.protocolState} />
            </div>
          </div>

          {/* Pending decisions stay in view while the conversation scrolls to its end. */}
          {(state.permissions.length > 0 || state.modeRequest) && (
            <div className="decision-dock flex shrink-0 flex-col items-center gap-3">
              <PermissionPromptCard prompts={state.permissions} onAnswer={socket.answerPermission} />
              <ModeSwitchCard request={state.modeRequest} onAnswer={socket.answerModeSwitch} />
            </div>
          )}

          <PromptLine
              label="Message the agent"
              placeholder={busy ? 'The agent is working…' : 'Type instead of speaking'}
              disabled={!connected}
              busy={busy}
              onSend={handleSendText}
              onStop={socket.interrupt}
              aside={mode === 'push-to-talk' ? <PushToTalkControl onTalkingChange={onTalkingChange} /> : undefined}
              contextControls={
                <AgentComposerControls
                  backends={state.backends}
                  selection={selection}
                  onSelectionChange={handleSelectionChange}
                  folder={state.folder}
                  pickingFolder={state.pickingFolder}
                  onPickFolder={handlePickFolder}
                  connected={connected}
                  modeControl={modeControl}
                />
              }
          />
        </Panel>

        <div className="shell-seam" aria-hidden="true" />
        <div className="code-slot" aria-hidden={!showCode} inert={!showCode}>
          {code && <CodePane code={code.text} name={code.name} lang={code.lang} label="Code" onClose={() => setClosedCodeId(code.id)} />}
        </div>
      </div>

    </div>
  )
}

export default AgentApp
