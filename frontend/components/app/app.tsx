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

// Sub-component to monitor connection states and handle device permissions
function MainContent({ appConfig }: { appConfig: AppConfig }) {
  const connectionState = useConnectionState();
  const [micPermissionDenied, setMicPermissionDenied] = useState(false);

  // 🛡️ Step 4: Handle microphone permission errors
  useEffect(() => {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        // Microphone enabled properly, close the stream tracks
        stream.getTracks().forEach((track) => track.stop());
        setMicPermissionDenied(false);
      })
      .catch((err) => {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setMicPermissionDenied(true);
        }
      });
  }, []);

  // Show clear error block screen if microphone access is blocked by the user
  // Show clear error block screen if microphone access is blocked by the user
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

  // 🕒 Step 2: Connecting State UI Layer
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
    <main className="grid h-svh grid-cols-1 place-content-center">
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
