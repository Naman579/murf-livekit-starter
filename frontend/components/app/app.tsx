'use client';

import { useMemo, useEffect, useState } from 'react';
import { TokenSource, ConnectionState } from 'livekit-client';
import { useSession, useConnectionState } from '@livekit/components-react'; 
import { WarningIcon } from '@phosphor-icons/react/dist/ssr';
import type { AppConfig } from '@/app-config';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { ViewController } from '@/components/app/view-controller';
import { Toaster } from '@/components/ui/sonner';
import { useAgentErrors } from '@/hooks/useAgentErrors';
import { useDebugMode } from '@/hooks/useDebug';
import { getSandboxTokenSource } from '@/lib/utils';

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';

function AppSetup() {
  useDebugMode({ enabled: IN_DEVELOPMENT });
  useAgentErrors();

  return null;
}

interface AppProps {
  appConfig: AppConfig;
}

function MainContent({ appConfig }: { appConfig: AppConfig }) {
  const connectionState = useConnectionState();
  const [micPermissionDenied, setMicPermissionDenied] = useState(false);
  
  // 🌟 Streak Data State & Modal Toggle State
  const [showStreakModal, setShowStreakModal] = useState(false);
  const [streakData] = useState({
    count: 5,
    startDate: '30 Aug 2026',
    todayDate: new Date().toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    })
  });

  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        stream.getTracks().forEach((track) => track.stop());
        setMicPermissionDenied(false);
      })
      .catch((err) => {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setMicPermissionDenied(true);
        }
      });
  }, []);

  if (micPermissionDenied) {
    return (
      <main className="fixed inset-0 z-50 flex items-center justify-center bg-red-50 p-6">
        <div className="flex flex-col items-center justify-center max-w-md bg-white border-2 border-red-200 rounded-3xl p-8 shadow-xl space-y-4">
          <div className="w-16 h-16 bg-red-100 text-red-600 rounded-full flex items-center justify-center text-3xl font-bold animate-bounce">
            ⚠️
          </div>
          
          <h2 className="text-2xl font-black text-red-600 tracking-wide">
            Microphone is Blocked!
          </h2>
          
          <p className="text-gray-600 font-semibold text-sm leading-relaxed text-center">
            Shiksha cannot hear your brilliant answers because the microphone is turned off. 
          </p>

          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-left w-full text-xs text-amber-900 space-y-2">
            <p className="font-bold text-center border-b border-amber-200 pb-1">💡 How to enable it:</p>
            <p><strong>1.</strong> Look at the top left corner near your browser URL bar.</p>
            <p><strong>2.</strong> Click on the small 🔒 <strong>Lock</strong> or 🎤 <strong>Microphone</strong> icon.</p>
            <p><strong>3.</strong> Change the Microphone setting from <strong>Block</strong> to <strong>Allow</strong>.</p>
            <p><strong>4.</strong> Refresh this page to start learning! 🚀</p>
          </div>
        </div>
      </main>
    );
  }

  if (connectionState === ConnectionState.Connecting) {
    return (
      <main className="grid h-svh grid-cols-1 place-content-center bg-background text-center p-6">
        <div className="flex flex-col items-center justify-center space-y-4">
          <div className="animate-spin rounded-full h-16 w-16 border-t-4 border-b-4 border-violet-600 border-t-transparent"></div>
          <h2 className="text-2xl font-black text-violet-600 animate-pulse tracking-wide">
            ✨ Shiksha is joining the class...
          </h2>
          <p className="text-gray-500 font-medium max-w-xs">
            Hold tight, little learner! Magical doors are opening... 🚪🌟
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="relative grid h-svh grid-cols-1 place-content-center">
      {/* 🔥 Vector Animated Fire Button */}
      {connectionState === ConnectionState.Connected && (
        <div className="fixed top-16 right-8 z-50">
          <button
            onClick={() => setShowStreakModal(!showStreakModal)}
            className="p-1.5 rounded-2xl bg-orange-950/30 border border-orange-500/30 backdrop-blur-md hover:scale-110 active:scale-95 transition-all duration-200 shadow-lg shadow-orange-950/40 cursor-pointer flex items-center justify-center"
            title="Click to view Streak details"
          >
            {/* 🖼️ Custom Fire Animated Image/GIF */}
            <img 
              src="/fire-streak.gif" 
              alt="Fire Streak" 
              className="w-8 h-8 object-contain filter drop-shadow-[0_0_10px_rgba(249,115,22,0.8)] select-none pointer-events-none" 
            />
          </button>

          {/* 📊 Streak Details Popover Card */}
          {showStreakModal && (
            <div className="absolute right-0 mt-3 w-64 p-4 rounded-2xl bg-zinc-900/95 border border-zinc-800 backdrop-blur-xl shadow-2xl text-white space-y-3 animate-in fade-in slide-in-from-top-2 duration-200 z-50">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <div className="flex items-center gap-2">
                  <img src="/fire-streak.gif" alt="Fire" className="w-5 h-5 object-contain" />
                  <span className="font-bold text-sm text-orange-400">Daily Streak</span>
                </div>
                <button 
                  onClick={() => setShowStreakModal(false)}
                  className="text-zinc-400 hover:text-white text-xs font-bold px-1.5 py-0.5 rounded-md hover:bg-zinc-800"
                >
                  ✕
                </button>
              </div>

              <div className="text-center py-2 bg-orange-950/30 rounded-xl border border-orange-500/20">
                <p className="text-3xl font-extrabold text-orange-400">{streakData.count}</p>
                <p className="text-[11px] font-medium text-orange-200/80 uppercase tracking-wider">Days Active Streak</p>
              </div>

              <div className="space-y-1.5 text-xs text-zinc-300">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Today:</span>
                  <span className="font-semibold text-zinc-200">{streakData.todayDate}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Streak Started:</span>
                  <span className="font-semibold text-zinc-200">{streakData.startDate}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <ViewController appConfig={appConfig} />
    </main>
  );
}

export function App({ appConfig }: AppProps) {
  const tokenSource = useMemo(() => {
    return typeof process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string'
      ? getSandboxTokenSource(appConfig)
      : TokenSource.endpoint('/api/token');
  }, [appConfig]);

  const session = useSession(
    tokenSource,
    appConfig.agentName ? { agentName: appConfig.agentName } : undefined
  );

  return (
    <AgentSessionProvider session={session}>
      <AppSetup />
      
      <MainContent appConfig={appConfig} />

      <StartAudioButton label="Start Audio" />
      <Toaster
        icons={{
          warning: <WarningIcon weight="bold" />,
        }}
        position="top-center"
        className="toaster group"
        style={
          {
            '--normal-bg': 'var(--popover)',
            '--normal-text': 'var(--popover-foreground)',
            '--normal-border': 'var(--border)',
          } as React.CSSProperties
        }
      />
    </AgentSessionProvider>
  );
}
