import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';

const wasmPath = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.0/wasm';
const modelPath = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';

export default function HandTrackingOverlay({ videoRef }: { videoRef: RefObject<HTMLVideoElement | null> }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState('Loading hand tracking…');

  useEffect(() => {
    const videoElement = videoRef.current;
    const canvasElement = canvasRef.current;
    if (!videoElement || !canvasElement) {
      setStatus('Hand tracking is unavailable in this browser.');
      return;
    }
    const drawingContext = canvasElement.getContext('2d');
    if (!drawingContext) {
      setStatus('Hand tracking is unavailable in this browser.');
      return;
    }
    const video: HTMLVideoElement = videoElement;
    const canvas: HTMLCanvasElement = canvasElement;
    const context: CanvasRenderingContext2D = drawingContext;

    let active = true;
    let frame = 0;
    let lastVideoTime = -1;
    let previousHandCount = -1;
    let landmarker: import('@mediapipe/tasks-vision').HandLandmarker | undefined;

    async function start() {
      try {
        const { DrawingUtils, FilesetResolver, HandLandmarker } = await import('@mediapipe/tasks-vision');
        const fileset = await FilesetResolver.forVisionTasks(wasmPath);
        const task = await HandLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: modelPath },
          runningMode: 'VIDEO',
          numHands: 2,
        });

        if (!active) {
          task.close();
          return;
        }

        landmarker = task;
        const drawing = new DrawingUtils(context);

        function detectFrame() {
          if (!active || !landmarker) return;
          frame = window.requestAnimationFrame(detectFrame);

          if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.currentTime === lastVideoTime) return;
          lastVideoTime = video.currentTime;

          if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
          }

          context.clearRect(0, 0, canvas.width, canvas.height);
          const result = landmarker.detectForVideo(video, performance.now());
          result.landmarks.forEach(landmarks => {
            drawing.drawConnectors(landmarks, HandLandmarker.HAND_CONNECTIONS, {
              color: '#78e0ad',
              lineWidth: Math.max(2, canvas.width / 400),
            });
            drawing.drawLandmarks(landmarks, {
              color: '#ffffff',
              fillColor: '#328866',
              lineWidth: 1,
              radius: Math.max(2, canvas.width / 240),
            });
          });

          if (result.landmarks.length !== previousHandCount) {
            previousHandCount = result.landmarks.length;
            setStatus(result.landmarks.length
              ? `${result.landmarks.length} hand${result.landmarks.length === 1 ? '' : 's'} detected.`
              : 'No hands detected.');
          }
        }

        setStatus('Hand tracking is ready. Camera frames stay on this device.');
        frame = window.requestAnimationFrame(detectFrame);
      } catch (cause) {
        console.error('LIFEKEY hand tracking could not start:', cause);
        if (active) setStatus('Hand tracking could not load. Check your connection and try again.');
      }
    }

    void start();
    return () => {
      active = false;
      window.cancelAnimationFrame(frame);
      landmarker?.close();
      context.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [videoRef]);

  return (
    <>
      <canvas ref={canvasRef} className="hand-tracking-overlay" aria-hidden="true" />
      <span className="hand-tracking-status" role="status" aria-live="polite">{status}</span>
    </>
  );
}
