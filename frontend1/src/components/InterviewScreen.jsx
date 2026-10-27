import { useEffect, useRef, useState } from "react";
import {
  CameraOff,
  Send,
  LogOut,
  UserRound,
  Clock,
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  TriangleAlert,
  Eye,
} from "lucide-react";
import './Interview.css';

import {
  initializeFaceDetector,
  detectFace,
  getAffectSignal,
} from "../services/faceDetection";
import InterviewerFace from "./InterviewerFace";
import { CodingProblemPanel, CodingWorkspace } from "./CodingRound";
import { DesignProblemPanel, DesignWorkspace } from "./DesignRound";
import { analyzeInterviewDesign, getQuestionAudio, runInterviewCode } from "../services/interviewContext";

/*
 * This screen is a dumb renderer over the backend-owned interview state
 * machine (see app/modules/interview/service.py). `session` is whatever
 * the last /interview/sessions response was: { state, question,
 * question_number, total_questions, time_remaining_seconds, context }.
 * It never invents its own notion of "which question we're on" or
 * "whether the interview is over" - that always comes from the server,
 * including after a page refresh.
 */
// Speech-synthesis duration is estimated from text length at a slow,
// safely-overestimated rate (characters/sec) so the watchdog never fires
// before a real utterance of that length could plausibly finish.
const SPEECH_CHARS_PER_SEC = 15;
const SPEECH_WATCHDOG_BUFFER_MS = 4000;
const SPEECH_WATCHDOG_MIN_MS = 8000;
const SPEECH_WATCHDOG_MAX_MS = 45000;
// Rendering question audio on the backend takes a few seconds.
const AUDIO_FETCH_ALLOWANCE_MS = 20000;

function estimateSpeechMs(text) {
  const estimatedMs = Math.ceil(text.length / SPEECH_CHARS_PER_SEC) * 1000;

  return Math.min(
    SPEECH_WATCHDOG_MAX_MS,
    Math.max(SPEECH_WATCHDOG_MIN_MS, estimatedMs + SPEECH_WATCHDOG_BUFFER_MS)
  );
}

// Averages this question's collected MediaPipe affect samples into one
// small object, or null if the camera was unavailable/denied/no face was
// ever detected during the answer window.
const averageAffectSamples = (samples) => {
  if (!samples || !samples.length) {
    return null;
  }

  const keys = Object.keys(samples[0]);
  const averaged = {};

  for (const key of keys) {
    const sum = samples.reduce((total, s) => total + s[key], 0);
    averaged[key] = Math.round((sum / samples.length) * 1000) / 1000;
  }

  return averaged;
};

// Prefers a natural-sounding English voice. Voices can load late (Chrome
// fills the list asynchronously); if none are ready the browser default
// is used.
function pickEnglishVoice(synth) {
  const voices = synth.getVoices?.() || [];
  const english = voices.filter((v) => /^en(-|_|$)/i.test(v.lang));

  return (
    english.find((v) => /natural|google|samantha|aria|jenny/i.test(v.name)) ||
    english.find((v) => v.lang?.toLowerCase().replace("_", "-") === "en-us") ||
    english[0] ||
    null
  );
}

// Joins two pieces of answer text with a single space between them.
function joinText(before, after) {
  if (!before) return after;
  if (!after) return before;
  return `${before.trimEnd()} ${after.trimStart()}`;
}

export default function InterviewScreen({
  session,
  onEndInterview,
  onReadyForAnswer,
  onSubmitAnswer,
  onTimeExpired,
  onProctoringEvent,
  onSync,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const syncIntervalRef = useRef(null);
  const recognitionRef = useRef(null);
  // True from "Start Answer" until the candidate (or submit / exit / timeout /
  // tab-hide) stops it. The browser ends recognition on its own after pauses
  // or ~60s; while this is true we restart it instead of treating that as Stop.
  const wantListeningRef = useRef(false);
  // Answer text that existed before the current recognition run, so each
  // run (and each automatic restart) appends instead of overwriting.
  const committedAnswerRef = useRef("");
  const answerRef = useRef("");
  const lastSpokenQuestionRef = useRef(null);

  // Guards the in-flight speakQuestion call: only one of {watchdog timeout,
  // utterance onend/onerror, forced-by-tab-hide} may actually invoke onDone.
  const speechDoneRef = useRef(null);
  const speechWatchdogRef = useRef(null);
  // The <audio> element currently reading the question, if any.
  const audioRef = useRef(null);

  const faceDetectionIntervalRef = useRef(null);
  const faceDetectorRef = useRef(null);
  const lastFaceDetectedRef = useRef(null);

  // Per-question MediaPipe blendshape-derived affect samples, reset whenever
  // a new question starts; averaged into one small object on submit (Phase 9b).
  const emotionSamplesRef = useRef([]);

  const [cameraAvailable, setCameraAvailable] = useState(false);
  const [answer, setAnswer] = useState("");

  // Coding round: the question is a problem solved in an editor.
  const coding = session.coding;
  const [code, setCode] = useState(coding?.code ?? "");
  const [runResult, setRunResult] = useState(null);
  const [running, setRunning] = useState(false);

  // Design-lab round: the question is an architecture edited on a canvas.
  const design = session.design;
  const [designGraph, setDesignGraph] = useState(design?.graph ?? null);
  const [designExplanation, setDesignExplanation] = useState("");
  const [ending, setEnding] = useState(false);
  const [endError, setEndError] = useState("");
  const endDialogRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [timeLeft, setTimeLeft] = useState(session.time_remaining_seconds ?? 0);

  // Voice states
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  // Set when the browser refuses or fails to read the question aloud, so the
  // candidate sees why it's silent and can replay it with a click.
  const [speechIssue, setSpeechIssue] = useState("");
  const [speechSupported, setSpeechSupported] =
    useState(true);

  // Face detection states
  const [faceDetected, setFaceDetected] =
    useState(false);

  const [faceDetectionReady, setFaceDetectionReady] =
    useState(false);

  // Browser visibility state
  const [pageVisible, setPageVisible] =
    useState(true);

  /*
   * Start camera, timer and speech recognition
   */
  useEffect(() => {
    startCamera();
    startFaceDetection();

    timerRef.current = setInterval(() => {
      setTimeLeft((previous) => {
        if (previous <= 1) {
          clearInterval(timerRef.current);
          return 0;
        }

        return previous - 1;
      });
    }, 1000);

    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechSupported(false);
    } else {
      const recognition = new SpeechRecognition();

      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setIsListening(true);
        setError("");
      };

      recognition.onresult = (event) => {
        // In continuous mode event.results holds everything heard in this
        // run (final + in-progress), so rebuild from the start each time.
        let transcript = "";

        for (let i = 0; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }

        setAnswer(joinText(committedAnswerRef.current, transcript));
      };

      recognition.onerror = (event) => {
        console.error(
          "Speech recognition error:",
          event.error
        );

        // Silence and our own restarts are expected; onend restarts.
        if (event.error === "no-speech" || event.error === "aborted") {
          return;
        }

        wantListeningRef.current = false;

        setError(
          event.error === "not-allowed" || event.error === "service-not-allowed"
            ? "Microphone access was blocked. Allow it in the browser, or type your answer."
            : "Voice recognition failed. You can type your answer instead."
        );

        setIsListening(false);
      };

      recognition.onend = () => {
        if (!wantListeningRef.current) {
          setIsListening(false);
          return;
        }

        // The browser stopped by itself (pause or time limit): keep what was
        // said so far and carry on listening.
        committedAnswerRef.current = answerRef.current;

        try {
          recognition.start();
        } catch (err) {
          console.error("Could not restart speech recognition:", err);
          wantListeningRef.current = false;
          setIsListening(false);
        }
      };

      recognitionRef.current = recognition;
    }

    return () => {
      stopCamera();

      clearInterval(timerRef.current);
      clearInterval(syncIntervalRef.current);

      clearInterval(
        faceDetectionIntervalRef.current
      );

      wantListeningRef.current = false;
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      stopSpeech();

      // This cleanup also runs on React's dev-mode StrictMode double-invoke
      // (mount -> cleanup -> mount again). The cancel() above silences the
      // question, so forget that it was spoken: the remount's speaking
      // effect then reads it again. The cancelled utterance's late onerror
      // can't advance the interview because each speakQuestion call has its
      // own token (see finishSpeaking).
      lastSpokenQuestionRef.current = null;
    };
    // Mount-only: camera, face detection and the timer start once per interview.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /*
   * Timer reaches zero: tell the parent so it can resync with the
   * backend, which owns the real clock and will have already moved the
   * session into TIME_EXPIRED / REPORT.
   */
  useEffect(() => {
    if (timeLeft === 0) {
      clearInterval(timerRef.current);

      stopCamera();

      clearInterval(
        faceDetectionIntervalRef.current
      );

      wantListeningRef.current = false;
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      stopSpeech();

      clearTimeout(speechWatchdogRef.current);
      speechDoneRef.current = null;

      setIsListening(false);
      setIsSpeaking(false);

      if (onTimeExpired) {
        onTimeExpired();
      }
    }
  }, [timeLeft, onTimeExpired]);

  /*
   * Tab visibility: some browsers silently pause speechSynthesis while
   * backgrounded (and never fire onend/onerror once it's cancelled), so
   * rather than trying to resume speech on refocus, we treat losing focus
   * as "done speaking" and let the candidate answer whenever they're back.
   * Also reports tab-switch events to the backend and forces a resync on
   * refocus, since setInterval-based timeLeft can drift while backgrounded.
   */
  useEffect(() => {
    const handleVisibilityChange = () => {
      const visible = !document.hidden;

      setPageVisible(visible);

      if (onProctoringEvent) {
        onProctoringEvent(visible ? "tab_visible" : "tab_hidden");
      }

      if (!visible) {
        stopSpeech();

        wantListeningRef.current = false;
        if (recognitionRef.current) {
          recognitionRef.current.stop();
        }

        setIsListening(false);

        if (speechDoneRef.current) {
          finishSpeaking(speechDoneRef.current);
        }
      } else if (onSync) {
        onSync();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onProctoringEvent, onSync]);

  /*
   * Periodically resync against the backend's authoritative session/clock
   * even if the tab never loses focus, so a throttled timer can't drift
   * far from the server before the candidate notices.
   */
  useEffect(() => {
    if (!onSync) return;

    syncIntervalRef.current = setInterval(() => {
      onSync();
    }, 20000);

    return () => clearInterval(syncIntervalRef.current);
  }, [onSync]);

  /*
   * The backend is the source of truth for time remaining; resync our
   * local countdown display whenever a fresh session comes in (answer
   * submitted, listening acknowledged, periodic/refocus sync, ...).
   */
  useEffect(() => {
    setTimeLeft(session.time_remaining_seconds ?? 0);
  }, [session.time_remaining_seconds]);

  /*
   * Speak the AI's question whenever the backend hands us a new one
   * while it's in AI_SPEAKING. Once speech ends (or immediately, if
   * speech isn't supported), tell the backend we're ready for the
   * candidate's answer, which moves it into LISTENING.
   */
  useEffect(() => {
    if (session.state !== "AI_SPEAKING" || !session.question) {
      return;
    }

    const key = `${session.question_number}:${session.question}`;

    if (lastSpokenQuestionRef.current === key) {
      return;
    }

    lastSpokenQuestionRef.current = key;
    emotionSamplesRef.current = [];

    if ("speechSynthesis" in window) {
      speakQuestion(session.question, onReadyForAnswer);
    } else {
      onReadyForAnswer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.state, session.question_number, session.question]);

  /*
   * Start webcam
   */
  const startCamera = async () => {
    try {
      const stream =
        await navigator.mediaDevices.getUserMedia({
          video: true,
        });

      streamRef.current = stream;
      setCameraAvailable(true);

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      console.error(
        "Camera access denied:",
        err
      );

      setCameraAvailable(false);
    }
  };

  /*
   * Stop webcam
   */
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current
        .getTracks()
        .forEach((track) => {
          track.stop();
        });

      streamRef.current = null;
    }
  };

  /*
   * Initialize face detector
   */
  const startFaceDetection = async () => {
    try {
      const detector =
        await initializeFaceDetector();

      faceDetectorRef.current = detector;

      setFaceDetectionReady(true);

      startFaceMonitoring();
    } catch (err) {
      console.error(
        "Face detector initialization failed:",
        err
      );

      setFaceDetectionReady(false);
    }
  };

  /*
   * Monitor face approximately once per second
   */
  const startFaceMonitoring = () => {
    clearInterval(
      faceDetectionIntervalRef.current
    );

    faceDetectionIntervalRef.current =
      setInterval(() => {
        if (
          !videoRef.current ||
          !faceDetectorRef.current ||
          document.hidden
        ) {
          return;
        }

        try {
          const timestamp = performance.now();
          const detected = detectFace(
            videoRef.current,
            timestamp
          );

          setFaceDetected(detected);

          if (
            onProctoringEvent &&
            lastFaceDetectedRef.current !== null &&
            lastFaceDetectedRef.current !== detected
          ) {
            onProctoringEvent(detected ? "face_regained" : "face_lost");
          }

          lastFaceDetectedRef.current = detected;

          if (detected) {
            const affect = getAffectSignal(videoRef.current, timestamp);

            if (affect) {
              emotionSamplesRef.current.push(affect);
            }
          }
        } catch (err) {
          console.error(
            "Face detection error:",
            err
          );
        }
      }, 1000);
  };

  /*
   * Resolves the currently in-flight speakQuestion call exactly once,
   * whichever of {onend, onerror, watchdog timeout, tab-hide} gets there
   * first. Clears the watchdog and the "in-flight" marker so a late event
   * from a since-abandoned utterance can't double-fire onDone.
   */
  const finishSpeaking = (token) => {
    if (!token || speechDoneRef.current !== token) {
      return;
    }

    speechDoneRef.current = null;

    if (speechWatchdogRef.current) {
      clearTimeout(speechWatchdogRef.current);
      speechWatchdogRef.current = null;
    }

    setIsSpeaking(false);

    if (token.onDone) token.onDone();
  };

  /*
   * Text-to-speech for interviewer. Browsers occasionally drop an
   * utterance silently - neither onend nor onerror fires - e.g. after tab
   * backgrounding, with certain voice-pack states, or if speak() is called
   * while the queue is paused. A watchdog timeout guarantees onDone always
   * runs, so the candidate is never stuck on AI_SPEAKING.
   */
  // Safety net: if neither "ended" nor "error" ever arrives (a real failure
  // mode for browser speech after tab backgrounding), stop waiting and let
  // the candidate answer anyway.
  const armSpeechWatchdog = (token, ms) => {
    if (speechWatchdogRef.current) {
      clearTimeout(speechWatchdogRef.current);
    }

    speechWatchdogRef.current = setTimeout(() => {
      if (speechDoneRef.current !== token) return;

      console.warn(
        "Speech watchdog fired: no end/error event within",
        ms,
        "ms - forcing the interview to advance."
      );

      stopSpeech();
      finishSpeaking(token);
    }, ms);
  };

  // Stops whatever is reading the question: server audio or browser speech.
  const stopSpeech = () => {
    const audio = audioRef.current;

    if (audio) {
      audioRef.current = null;
      audio.onplaying = null;
      audio.onended = null;
      audio.onerror = null;
      audio.onloadedmetadata = null;
      audio.pause();
      URL.revokeObjectURL(audio.src);
    }

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  };

  /*
   * Reads the question aloud. Prefers audio rendered by the backend (a normal
   * audio file, so it plays wherever the tab can play sound); falls back to
   * the browser's own speech if that's unavailable.
   */
  const speakQuestion = (question, onDone) => {
    if (!question) {
      if (onDone) onDone();
      return;
    }

    // A fresh object per call, so events from an older (cancelled) attempt
    // can never resolve this one.
    const token = { onDone };
    speechDoneRef.current = token;

    stopSpeech();

    // Allow time to fetch the audio on top of reading it.
    armSpeechWatchdog(token, estimateSpeechMs(question) + AUDIO_FETCH_ALLOWANCE_MS);

    getQuestionAudio(session.session_id)
      .then((blob) => {
        if (speechDoneRef.current !== token) return;

        const audio = new Audio(URL.createObjectURL(blob));
        audioRef.current = audio;

        audio.onloadedmetadata = () => {
          if (Number.isFinite(audio.duration)) {
            armSpeechWatchdog(token, audio.duration * 1000 + SPEECH_WATCHDOG_BUFFER_MS);
          }
        };

        audio.onplaying = () => {
          if (speechDoneRef.current === token) {
            setIsSpeaking(true);
            setSpeechIssue("");
          }
        };

        audio.onended = () => {
          stopSpeech();
          finishSpeaking(token);
        };

        audio.onerror = () => {
          console.warn("Question audio could not be played; using browser speech.");
          stopSpeech();
          speakWithBrowser(question, token);
        };

        audio.play().catch((err) => {
          if (speechDoneRef.current !== token) return;

          if (err?.name === "NotAllowedError") {
            setSpeechIssue("Your browser blocked the interviewer's voice. Click Replay question to hear it.");
            stopSpeech();
            finishSpeaking(token);
            return;
          }

          stopSpeech();
          speakWithBrowser(question, token);
        });
      })
      .catch((err) => {
        if (speechDoneRef.current !== token) return;
        console.warn("Question audio unavailable; using browser speech.", err?.message);
        speakWithBrowser(question, token);
      });
  };

  const speakWithBrowser = (question, token) => {
    if (!("speechSynthesis" in window)) {
      finishSpeaking(token);
      return;
    }

    const synth = window.speechSynthesis;

    // speechSynthesis can get stuck reporting speaking/pending true from a
    // prior utterance; cancel() defensively so the browser reliably fires
    // events for this one. Chrome silently drops a speak() issued in the
    // same tick as cancel(), so give it a moment first.
    const needsReset = synth.speaking || synth.pending;
    synth.cancel();

    const utterance =
      new SpeechSynthesisUtterance(question);

    utterance.rate = 0.95;
    utterance.pitch = 1;
    utterance.volume = 1;
    utterance.lang = "en-US";

    try {
      const voice = pickEnglishVoice(synth);
      if (voice) utterance.voice = voice;
    } catch (err) {
      // A bad voice must never stop the question being read; fall back to
      // the browser default.
      console.warn("Could not select a speech voice:", err);
    }

    utterance.onstart = () => {
      if (speechDoneRef.current === token) {
        setIsSpeaking(true);
        setSpeechIssue("");
      }
    };

    utterance.onend = () => {
      finishSpeaking(token);
    };

    utterance.onerror = (event) => {
      // "interrupted"/"canceled" are our own cancel() calls, not failures.
      if (
        speechDoneRef.current === token &&
        event?.error &&
        event.error !== "interrupted" &&
        event.error !== "canceled"
      ) {
        console.warn("Interviewer speech failed:", event.error);
        setSpeechIssue(
          event.error === "not-allowed"
            ? "Your browser blocked the interviewer's voice. Click Replay question to hear it."
            : "The interviewer's voice couldn't play. Click Replay question to try again."
        );
      }

      finishSpeaking(token);
    };

    const speakNow = () => {
      if (speechDoneRef.current !== token) return;
      // Chrome can leave the queue paused after tab switches.
      synth.resume();
      synth.speak(utterance);
    };

    if (needsReset) {
      setTimeout(speakNow, 80);
    } else {
      speakNow();
    }

    armSpeechWatchdog(token, estimateSpeechMs(question));
  };

  useEffect(() => {
    answerRef.current = answer;
  }, [answer]);

  // Reads the current question again. A click always counts as a user
  // gesture, so this also works when the browser blocked automatic speech.
  const replayQuestion = () => {
    if (!session?.question) return;

    stopListening();
    setSpeechIssue("");

    // Still waiting to hand over to the candidate? Finish that handover once
    // this replay ends; otherwise just read it again.
    speakQuestion(
      session.question,
      session.state === "AI_SPEAKING" ? onReadyForAnswer : undefined
    );
  };

  const stopListening = () => {
    wantListeningRef.current = false;

    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }

    setIsListening(false);
  };

  /*
   * Start / stop microphone
   */
  const toggleListening = () => {
    if (
      !speechSupported ||
      !recognitionRef.current
    ) {
      setError(
        "Voice recognition is not supported in this browser. Please type your answer."
      );

      return;
    }

    if (isListening) {
      stopListening();
      return;
    }

    stopSpeech();
    setIsSpeaking(false);

    setError("");

    wantListeningRef.current = true;
    committedAnswerRef.current = answerRef.current;

    try {
      recognitionRef.current.start();
    } catch (err) {
      console.error(
        "Could not start speech recognition:",
        err
      );
      wantListeningRef.current = false;
    }
  };

  /*
   * Format timer
   */
  const formatTime = (seconds) => {
    const minutes = Math.floor(
      seconds / 60
    );

    const remainingSeconds =
      seconds % 60;

    return `${String(minutes).padStart(
      2,
      "0"
    )}:${String(
      remainingSeconds
    ).padStart(2, "0")}`;
  };

  const canAnswer = session.state === "LISTENING";

  // A new coding question starts from its saved draft (or the starter code).
  const codingProblemId = coding?.problem.id;
  useEffect(() => {
    setCode(coding?.code ?? "");
    setRunResult(null);
    // Only when the question changes, not on every session sync.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.question_number, codingProblemId]);

  // A new design exercise starts from its saved draft (or the starter).
  const designPromptId = design?.prompt.id;
  useEffect(() => {
    setDesignGraph(design?.graph ?? null);
    setDesignExplanation("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.question_number, designPromptId]);

  // What the candidate is answering with: their code in the coding round,
  // their design (+ explanation) in the design round, otherwise the
  // spoken/typed answer.
  const currentAnswer = coding
    ? code
    : design
    ? JSON.stringify({ graph: designGraph, explanation: designExplanation })
    : answer;
  const hasCodeChanges = coding ? code.trim() !== coding.problem.starter_code.trim() : false;
  // Partial work worth grading if the interview is ended mid-question.
  const hasWorkInProgress = coding
    ? hasCodeChanges
    : design
    ? Boolean(designExplanation.trim()) || JSON.stringify(designGraph) !== JSON.stringify(design.graph)
    : Boolean(answer.trim());

  const analyzeDesign = (graph) => analyzeInterviewDesign(session.session_id, graph);

  const handleRun = async () => {
    if (!coding || running || !canAnswer) return;

    setRunning(true);
    setError("");

    try {
      setRunResult(await runInterviewCode(session.session_id, code));
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't run your code. Please try again.");
    } finally {
      setRunning(false);
    }
  };

  /*
   * Submit candidate answer
   */
  const handleSubmit = async () => {
    if (
      !currentAnswer.trim() ||
      submitting ||
      timeLeft === 0 ||
      !canAnswer
    ) {
      return;
    }

    stopListening();

    stopSpeech();

    setIsListening(false);
    setIsSpeaking(false);
    setError("");
    setSubmitting(true);

    try {
      await onSubmitAnswer(
        currentAnswer.trim(),
        averageAffectSamples(emotionSamplesRef.current)
      );

      setAnswer("");
      setRunResult(null);
      setDesignExplanation("");
    } catch (err) {
      console.error(
        "Answer submission failed:",
        err
      );

      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Something went wrong while submitting your answer."
      );
    } finally {
      setSubmitting(false);
    }
  };

  /*
   * End interview early: confirm, then score what was answered (including
   * an answer still being typed) and show the report.
   */
  const handleEnd = async () => {
    if (ending) return;

    setEnding(true);
    setEndError("");
    const inProgress = canAnswer && hasWorkInProgress ? currentAnswer.trim() : "";
    const affect = averageAffectSamples(emotionSamplesRef.current);

    // Quiet the room while the report is built. On success the report
    // replaces this screen and the unmount cleanup releases the camera.
    stopVoice();

    try {
      await onEndInterview(inProgress, affect);
    } catch (err) {
      setEndError(
        err?.response?.data?.detail || "Couldn't end the interview right now. Please try again."
      );
      setEnding(false);
    }
  };

  const stopVoice = () => {
    wantListeningRef.current = false;
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }

    stopSpeech();

    clearTimeout(speechWatchdogRef.current);
    speechDoneRef.current = null;

    setIsListening(false);
    setIsSpeaking(false);
  };

  const timerClass =
    timeLeft <= 60
      ? "timer-critical"
      : timeLeft <= 5 * 60
      ? "timer-warning"
      : "";

  const avatarState =
    session.state === "AI_SPEAKING" || isSpeaking
      ? "speaking"
      : session.state === "PROCESSING" || submitting
      ? "thinking"
      : isListening
      ? "listening"
      : "idle";

  const avatarStatusLabel = {
    idle: "Ready for your answer",
    speaking: "AI Interviewer is speaking",
    listening: "Listening to your answer",
    thinking: "Evaluating your answer",
  }[avatarState];

  const AvatarStatusIcon =
    avatarState === "speaking"
      ? Volume2
      : avatarState === "listening"
      ? Mic
      : avatarState === "thinking"
      ? Clock
      : VolumeX;

  return (
    <div className="interview-screen">

      {/* =========================
          TOP BAR
          ========================= */}
      <div className="interview-topbar">

        <div>
          <span className="interview-label">
            AI INTERVIEW
          </span>

          <h1>{session?.context?.target_role || "Live Interview"}</h1>

          {session?.context?.company && (
            <p className="interview-topbar-sub">
              {session.context.company}
            </p>
          )}
        </div>

        <div className="interview-topbar-actions">

          <div
            className={`interview-timer ${timerClass}`}
          >
            <Clock size={17} />

            <span>
              {formatTime(timeLeft)}
            </span>

            <small>
              remaining
            </small>
          </div>

          <button
            className="exit-interview-button"
            onClick={() => endDialogRef.current?.showModal()}
          >
            <LogOut size={16} />
            End Interview
          </button>

        </div>
      </div>

      {/* =========================
          PAGE VISIBILITY WARNING
          ========================= */}
      {!pageVisible && (
        <div className="page-warning">
          <div className="page-warning-icon">
            <TriangleAlert size={18} />
          </div>

          <div>
            <strong>Interview window inactive</strong>

            <span>
              Please return to this tab to continue your interview.
            </span>
          </div>
        </div>
      )}

      {/* =========================
          ROOM: interviewer stage on the left (full height),
          answer box and candidate camera stacked on the right
          ========================= */}
      <div className={`interview-room ${coding ? "coding-mode" : ""} ${design ? "coding-mode design-mode" : ""}`}>
        <div className="interview-stage">
          <div className="ai-avatar-block">
            <InterviewerFace state={avatarState} />

            <div className="ai-avatar-status" aria-live="polite">
              <AvatarStatusIcon size={15} />
              {avatarStatusLabel}
            </div>
          </div>

          <div className="question-block">
            <span className="question-number">
              Question{" "}
              {session?.question_number}
              {session?.total_questions ? ` of ${session.total_questions}` : ""}
            </span>

            <p className="question-text">
              {session?.question}
            </p>

            {"speechSynthesis" in window && session?.question && (
              <button
                type="button"
                className="replay-question-button"
                onClick={replayQuestion}
                disabled={isSpeaking || submitting}
              >
                <Volume2 size={15} />
                {isSpeaking ? "Speaking..." : "Replay question"}
              </button>
            )}

            {speechIssue && (
              <p className="speech-issue" role="status">
                {speechIssue}
              </p>
            )}
          </div>

          {coding && <CodingProblemPanel problem={coding.problem} />}
          {design && <DesignProblemPanel design={design} />}
        </div>

        <aside className="interview-side">
          {design ? (
            <DesignWorkspace
              key={design.prompt.id}
              design={design}
              onGraphChange={setDesignGraph}
              explanation={designExplanation}
              onExplanationChange={setDesignExplanation}
              analyze={analyzeDesign}
              onSubmit={handleSubmit}
              submitting={submitting}
              disabled={!canAnswer || timeLeft === 0}
              error={error}
            />
          ) : coding ? (
            <CodingWorkspace
              problem={coding.problem}
              code={code}
              onChange={setCode}
              onRun={handleRun}
              onSubmit={handleSubmit}
              running={running}
              submitting={submitting}
              disabled={!canAnswer || timeLeft === 0}
              result={runResult}
              error={error}
            />
          ) : (
          <div className="answer-section">

            <div className="answer-heading">
              <span>
                Your Answer
              </span>

              {isListening && (
                <div className="listening-indicator">
                  <span className="listening-dot"></span>
                  Listening...
                </div>
              )}
            </div>

            <textarea
              value={answer}
              onChange={(e) =>
                setAnswer(e.target.value)
              }
              placeholder={
                !canAnswer
                  ? "Please wait for the interviewer..."
                  : speechSupported
                  ? "Click Start Answer and speak, or type your answer..."
                  : "Type your answer..."
              }
              disabled={
                submitting ||
                timeLeft === 0 ||
                !canAnswer
              }
              rows={5}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  (e.ctrlKey || e.metaKey)
                ) {
                  handleSubmit();
                }
              }}
            />

            {error && (
              <div className="interview-error">
                {error}
              </div>
            )}

            <div className="answer-footer">

              <span>
                {speechSupported
                  ? "Review your transcript before submitting."
                  : "Voice recognition is unavailable. Type your answer."}
              </span>

              <div className="answer-actions">

                {/* MICROPHONE */}
                {speechSupported && (
                  <button
                    className={`voice-answer-button ${
                      isListening
                        ? "listening"
                        : ""
                    }`}
                    onClick={
                      toggleListening
                    }
                    disabled={
                      submitting ||
                      timeLeft === 0 ||
                      !canAnswer
                    }
                  >
                    {isListening ? (
                      <MicOff size={17} />
                    ) : (
                      <Mic size={17} />
                    )}

                    {isListening
                      ? "Stop Answer"
                      : "Start Answer"}
                  </button>
                )}

                {/* SUBMIT */}
                <button
                  className="submit-answer-button"
                  onClick={handleSubmit}
                  disabled={
                    !answer.trim() ||
                    submitting ||
                    timeLeft === 0 ||
                    !canAnswer
                  }
                >
                  <Send size={17} />

                  {submitting
                    ? "Evaluating..."
                    : "Submit Answer"}
                </button>

              </div>
            </div>
          </div>
          )}

          {/* CANDIDATE SELF-VIEW */}
          <div className="camera-panel">
            {cameraAvailable ? (
              <>
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="webcam"
                />

                <div className="camera-pip-label">
                  <UserRound size={11} />
                  You
                </div>

                {faceDetectionReady && (
                  <div
                    className={`presence-dot ${
                      faceDetected ? "presence-ok" : "presence-warning"
                    }`}
                    title={
                      faceDetected
                        ? "Candidate detected"
                        : "Face not detected — please stay visible"
                    }
                  >
                    {faceDetected ? (
                      <Eye size={12} />
                    ) : (
                      <TriangleAlert size={12} />
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="camera-placeholder">
                <CameraOff size={20} />
                Camera unavailable
              </div>
            )}
          </div>
        </aside>
      </div>

      <dialog
        ref={endDialogRef}
        className="end-interview-dialog"
        aria-labelledby="end-interview-title"
        onCancel={(e) => ending && e.preventDefault()}
      >
        <h2 id="end-interview-title">End the interview now?</h2>
        {endError && (
          <p className="interview-error" role="alert">
            {endError}
          </p>
        )}
        <p>
          You&apos;ll get your report and feedback for the questions answered so far
          {canAnswer && hasWorkInProgress
            ? coding
              ? ", including the code in your editor"
              : design
              ? ", including your current design"
              : ", including the answer you are typing"
            : ""}
          .
          Unanswered questions aren&apos;t counted.
        </p>
        <div className="end-interview-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => endDialogRef.current?.close()}
            disabled={ending}
          >
            Keep going
          </button>
          <button type="button" className="btn btn-primary" onClick={handleEnd} disabled={ending}>
            {ending ? "Preparing your report..." : "End and see report"}
          </button>
        </div>
      </dialog>
    </div>
  );
}
