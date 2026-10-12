import { useEffect, useRef } from 'react';
import { createPulseEngine } from './engine';

/**
 * Host for the procedural pixel world. The engine is created once per mount and
 * exposed to the parent through `engineRef` so WS packets and the POST response
 * can drive the animation.
 */
export default function PulseWorld({ engineRef, onStatus, onFps }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const engine = createPulseEngine(canvasRef.current, { onStatus, onFps });
    engineRef.current = engine;
    return () => {
      engine.dispose();
      engineRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full block pixel-art cursor-crosshair relative z-10"
    />
  );
}
