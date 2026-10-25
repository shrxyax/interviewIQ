import {
  FaceLandmarker,
  FilesetResolver,
} from "@mediapipe/tasks-vision";

/*
 * Phase 6 (presence) + Phase 9b (emotion/affect proxies) share one
 * MediaPipe FaceLandmarker instance and one detectForVideo() call per tick,
 * instead of running two separate models against the same webcam stream.
 * Blendshapes are reduced to three explainable 0-1 proxies - not a clinical
 * emotion classifier - see getAffectSignal below.
 */

let faceLandmarker = null;
let initializing = null;

const WASM_PATH =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm";

const MODEL_PATH =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

export const initializeFaceDetector = async () => {
  if (faceLandmarker) {
    return faceLandmarker;
  }

  if (initializing) {
    return initializing;
  }

  initializing = (async () => {
    const vision = await FilesetResolver.forVisionTasks(
      WASM_PATH
    );

    faceLandmarker =
      await FaceLandmarker.createFromOptions(
        vision,
        {
          baseOptions: {
            modelAssetPath: MODEL_PATH,
          },

          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: true,
          outputFacialTransformationMatrixes: false,
        }
      );

    return faceLandmarker;
  })();

  try {
    return await initializing;
  } finally {
    initializing = null;
  }
};

/*
 * Runs detection once per call site. detectFace/getAffectSignal both read
 * from this so a single frame only gets detected once per tick.
 */
const runDetection = (videoElement, timestamp) => {
  if (!faceLandmarker || !videoElement) {
    return null;
  }

  if (
    videoElement.readyState <
    HTMLMediaElement.HAVE_CURRENT_DATA
  ) {
    return null;
  }

  return faceLandmarker.detectForVideo(videoElement, timestamp);
};

export const detectFace = (
  videoElement,
  timestamp
) => {
  const result = runDetection(videoElement, timestamp);
  return Boolean(result && result.faceLandmarks && result.faceLandmarks.length > 0);
};

const categoryScore = (categories, name) => {
  const match = categories.find((c) => c.categoryName === name);
  return match ? match.score : 0;
};

/*
 * Reduces MediaPipe's face blendshapes into three interpretable 0-1 proxies
 * for one detection tick:
 *  - engagement: eyes open / attentive (inverse of blink/closure)
 *  - stress_proxy: brow tension + mouth pressing
 *  - positive_expression_proxy: smile intensity
 * These are heuristic proxies, never surfaced live to the candidate, and
 * explicitly not a claim of detecting a specific emotion.
 */
export const getAffectSignal = (
  videoElement,
  timestamp
) => {
  const result = runDetection(videoElement, timestamp);
  const shapes = result?.faceBlendshapes?.[0]?.categories;

  if (!shapes || !shapes.length) {
    return null;
  }

  const eyeBlink =
    (categoryScore(shapes, "eyeBlinkLeft") + categoryScore(shapes, "eyeBlinkRight")) / 2;

  const browTension =
    (categoryScore(shapes, "browDownLeft") + categoryScore(shapes, "browDownRight")) / 2;

  const mouthPress =
    (categoryScore(shapes, "mouthPressLeft") + categoryScore(shapes, "mouthPressRight")) / 2;

  const smile =
    (categoryScore(shapes, "mouthSmileLeft") + categoryScore(shapes, "mouthSmileRight")) / 2;

  return {
    engagement: Math.round((1 - eyeBlink) * 1000) / 1000,
    stress_proxy: Math.round(((browTension + mouthPress) / 2) * 1000) / 1000,
    positive_expression_proxy: Math.round(smile * 1000) / 1000,
  };
};
