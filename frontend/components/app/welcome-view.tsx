import { Button } from '@/components/ui/button';

// Bacchon ke liye ek mast learning icon
function WelcomeImage() {
  return (
    <div className="w-24 h-24 bg-yellow-400 rounded-full flex items-center justify-center shadow-xl border-4 border-white text-5xl animate-bounce mb-6">
      🎓
    </div>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref} className="w-full h-full flex items-center justify-center">
      <section className="bg-background flex flex-col items-center justify-center text-center p-6 max-w-md">
        {/* 🌟 Step 1: Fun Image / Icon */}
        <WelcomeImage />

        {/* 🎓 Step 1: Kid-friendly Typography & Copy */}
        <h1 className="text-3xl font-black text-violet-600 tracking-wide mb-2 animate-pulse">
          Hello, Little Learner! 🌟
        </h1>
        
        <p className="text-gray-600 max-w-prose pt-1 text-base leading-6 font-semibold">
          Ready to discover something amazing today? Tap below to start your magical class with Shiksha! 🧠✨
        </p>

        {/* 🚀 Step 2: One clear, prominent button to BEGIN (Ready State) */}
        <Button
          size="lg"
          onClick={onStartCall}
          className="mt-8 w-72 h-14 rounded-full bg-violet-600 hover:bg-violet-700 text-white font-black text-lg tracking-wide uppercase shadow-lg transition-transform transform hover:scale-105 active:scale-95 border-b-4 border-violet-800"
        >
          🚀 {startButtonText || "Let's Start!"}
        </Button>
      </section>

      {/* Footer Instructions tailored for students/parents */}
      <div className="fixed bottom-5 left-0 flex w-full items-center justify-center px-4">
        <p className="text-muted-foreground max-w-prose pt-1 text-xs leading-5 font-medium text-center">
          Make sure your 🎤 microphone is on so Shiksha can hear your brilliant answers!
        </p>
      </div>
    </div>
  );
};
