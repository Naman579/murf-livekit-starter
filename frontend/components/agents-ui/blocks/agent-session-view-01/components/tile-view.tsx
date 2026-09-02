import React, { useMemo } from 'react';
import { Track, ConnectionState } from 'livekit-client';
import { AnimatePresence, type MotionProps, motion } from 'motion/react';
import {
  type TrackReference,
  VideoTrack,
  useLocalParticipant,
  useTracks,
  useVoiceAssistant,
  useConnectionState,
  useRoomContext,
} from '@livekit/components-react';
import { cn } from '@/lib/shadcn/utils';
import { AudioVisualizer } from './audio-visualizer';

const ANIMATION_TRANSITION: MotionProps['transition'] = {
  type: 'spring',
  stiffness: 675,
  damping: 75,
  mass: 1,
};

const tileViewClassNames = {
  grid: [
    'h-full w-full',
    'grid gap-x-2 place-content-center',
    'grid-cols-[1fr_1fr] grid-rows-[90px_1fr_90px]',
  ],
  agentChatOpenWithSecondTile: ['col-start-1 row-start-1', 'self-center justify-self-end'],
  agentChatOpenWithoutSecondTile: ['col-start-1 row-start-1', 'col-span-2', 'place-content-center'],
  agentChatClosed: ['col-start-1 row-start-1', 'col-span-2 row-span-3', 'place-content-center'],
  secondTileChatOpen: ['col-start-2 row-start-1', 'self-center justify-self-start'],
  secondTileChatClosed: ['col-start-2 row-start-3', 'place-content-end'],
};

export function useLocalTrackRef(source: Track.Source) {
  const { localParticipant } = useLocalParticipant();
  const publication = localParticipant.getTrackPublication(source);
  const trackRef = useMemo<TrackReference | undefined>(
    () => (publication ? { source, participant: localParticipant, publication } : undefined),
    [source, publication, localParticipant]
  );
  return trackRef;
}

interface TileLayoutProps {
  chatOpen: boolean;
  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerWaveLineWidth?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerBarCount?: number;
}

export function TileLayout({
  chatOpen,
  audioVisualizerType = 'wave',
  audioVisualizerColor = '#8B5CF6',
  audioVisualizerColorShift,
  audioVisualizerBarCount,
  audioVisualizerRadialBarCount,
  audioVisualizerRadialRadius,
  audioVisualizerGridRowCount,
  audioVisualizerGridColumnCount,
  audioVisualizerWaveLineWidth,
}: TileLayoutProps) {
  const { videoTrack: agentVideoTrack, state: agentState } = useVoiceAssistant();
  const [screenShareTrack] = useTracks([Track.Source.ScreenShare]);
  const cameraTrack: TrackReference | undefined = useLocalTrackRef(Track.Source.Camera);
  const connectionState = useConnectionState();
  const room = useRoomContext();

  const isCameraEnabled = cameraTrack && !cameraTrack.publication.isMuted;
  const isScreenShareEnabled = screenShareTrack && !screenShareTrack.publication.isMuted;
  const hasSecondTile = isCameraEnabled || isScreenShareEnabled;

  const animationDelay = chatOpen ? 0 : 0.15;
  const isAvatar = agentVideoTrack !== undefined;
  const videoWidth = agentVideoTrack?.publication.dimensions?.width ?? 0;
  const videoHeight = agentVideoTrack?.publication.dimensions?.height ?? 0;

  // 🎤 Step 4: Handle Mic Permission State
  const [micError, setMicError] = React.useState<string | null>(null);

  React.useEffect(() => {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(() => setMicError(null))
      .catch((err) => {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          setMicError('Oops! Microphone access denied. Please enable your mic from browser settings to talk with Shiksha! 🎤');
        }
      });
  }, []);

  // 🎓 Step 2 & 3: Resolve current state text for the student
  const getStatusText = () => {
    if (connectionState === ConnectionState.Connecting) {
      return '✨ Shiksha is joining the class... Please wait!';
    }
    if (connectionState === ConnectionState.Connected) {
      if (agentState === 'speaking') return '🔊 Shiksha is speaking... Listen carefully!';
      if (agentState === 'listening') return '👂 I am listening to you... Speak now!';
      return '🧠 Shiksha is thinking...';
    }
    return '';
  };

  return (
    <div className="absolute inset-x-0 top-8 bottom-32 z-50 md:top-12 md:bottom-40 flex flex-col items-center justify-between">
      
      {/* 🚫 Mic Error Alert Box */}
      {micError && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-xl max-w-md text-center shadow-md font-medium mx-4 mb-4 animate-bounce">
          {micError}
        </div>
      )}

      {/* 📝 State Message Banner (Kids Edition) */}
      {connectionState !== ConnectionState.Disconnected && (
        <div className="bg-violet-600 text-white px-6 py-2 rounded-full font-bold text-lg shadow-lg tracking-wide border-2 border-white mb-6">
          {getStatusText()}
        </div>
      )}

      {/* Main Grid View */}
      <div className="relative mx-auto h-full w-full max-w-2xl px-4 md:px-0 flex-1">
        <div className={cn(tileViewClassNames.grid)}>
          
          {/* Agent Visualizer Block */}
          <div
            className={cn([
              'grid',
              !chatOpen && tileViewClassNames.agentChatClosed,
              chatOpen && hasSecondTile && tileViewClassNames.agentChatOpenWithSecondTile,
              chatOpen && !hasSecondTile && tileViewClassNames.agentChatOpenWithoutSecondTile,
            ])}
          >
            <AnimatePresence mode="popLayout">
              
              {/* Ready State / Call Ended State Controller */}
              {connectionState === ConnectionState.Disconnected && (
                <motion.div 
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center justify-center space-y-4 col-span-2 row-span-3"
                >
                  <div className="w-32 h-32 bg-yellow-400 rounded-full flex items-center justify-center shadow-xl border-4 border-white text-5xl animate-pulse">
                    🎓
                  </div>
                  <h2 className="text-2xl font-black text-violet-800 text-center">
                    Ready to learn something amazing?
                  </h2>
                  <p className="text-gray-600 text-sm text-center max-w-xs">
                    Tap the button below to start your conversation with Shiksha!
                  </p>
                </motion.div>
              )}

              {/* Connected Active State */}
              {connectionState !== ConnectionState.Disconnected && !isAvatar && (
                <motion.div
                  key="agent"
                  layoutId="agent"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ ...ANIMATION_TRANSITION, delay: animationDelay }}
                  className={cn('relative aspect-square h-[150px] w-[150px]')}
                >
                  {/* Dynamic Glowing Aura based on Agent Action */}
                  <div className={cn(
                    "absolute inset-0 rounded-full transition-all duration-500 blur-xl opacity-40",
                    agentState === 'speaking' ? "bg-green-400 scale-125" : "bg-violet-400 scale-100"
                  )} />

                  <AudioVisualizer
                    key="audio-visualizer"
                    initial={{ scale: 1 }}
                    animate={{ scale: chatOpen ? 0.4 : 1 }}
                    transition={{ ...ANIMATION_TRANSITION, delay: animationDelay }}
                    audioVisualizerType={audioVisualizerType}
                    audioVisualizerColor={audioVisualizerColor}
                    audioVisualizerColorShift={audioVisualizerColorShift}
                    audioVisualizerBarCount={audioVisualizerBarCount}
                    audioVisualizerRadialBarCount={audioVisualizerRadialBarCount}
                    audioVisualizerRadialRadius={audioVisualizerRadialRadius}
                    audioVisualizerGridRowCount={audioVisualizerGridRowCount}
                    audioVisualizerGridColumnCount={audioVisualizerGridColumnCount}
                    audioVisualizerWaveLineWidth={audioVisualizerWaveLineWidth}
                    isChatOpen={chatOpen}
                    className={cn(
                      'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2',
                      'bg-transparent border-none shadow-none outline-none'
                    )}
                    style={{ color: audioVisualizerColor }}
                  />
                </motion.div>
              )}

              {isAvatar && connectionState !== ConnectionState.Disconnected && (
                <motion.div
                  key="avatar"
                  layoutId="avatar"
                  initial={{ scale: 1, opacity: 1, filter: 'blur(20px)' }}
                  animate={{ filter: 'blur(0px)', borderRadius: chatOpen ? 6 : 12 }}
                  transition={{ ...ANIMATION_TRANSITION, delay: animationDelay }}
                  className={cn('overflow-hidden bg-black drop-shadow-xl', chatOpen ? 'h-[90px]' : 'h-auto w-full')}
                >
                  <VideoTrack
                    width={videoWidth}
                    height={videoHeight}
                    trackRef={agentVideoTrack}
                    className={cn(chatOpen && 'size-[90px] object-cover')}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* User Camera Block */}
          <div className={cn(['grid', chatOpen && tileViewClassNames.secondTileChatOpen, !chatOpen && tileViewClassNames.secondTileChatClosed])}>
            <AnimatePresence>
              {((cameraTrack && isCameraEnabled) || (screenShareTrack && isScreenShareEnabled)) && (
                <motion.div
                  key="camera"
                  layout="position"
                  layoutId="camera"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0 }}
                  transition={{ ...ANIMATION_TRANSITION, delay: animationDelay }}
                  className="aspect-square size-[90px] drop-shadow-lg"
                >
                  <VideoTrack
                    trackRef={cameraTrack || screenShareTrack}
                    width={(cameraTrack || screenShareTrack)?.publication.dimensions?.width ?? 0}
                    height={(cameraTrack || screenShareTrack)?.publication.dimensions?.height ?? 0}
                    className="bg-muted aspect-square size-[90px] rounded-xl object-cover border-2 border-violet-300"
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

        </div>
      </div>
    </div>
  );
}