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

export default function InterviewScreen({
  session,
  onExit,
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
  const lastSpokenQuestionRef = useRef(null);

  // Guards the in-flight speakQuestion call: only one of {watchdog timeout,
  // utterance onend/onerror, forced-by-tab-hide} may actually invoke onDone.
  const speechDoneRef = useRef(null);
  const speechWatchdogRef = useRef(null);

  const faceDetectionIntervalRef = useRef(null);
  const faceDetectorRef = useRef(null);
  const lastFaceDetectedRef = useRef(null);

  // Per-question MediaPipe blendshape-derived affect samples, reset whenever
  // a new question starts; averaged into one small object on submit (Phase 9b).
  const emotionSamplesRef = useRef([]);

  const [cameraAvailable, setCameraAvailable] = useState(false);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [timeLeft, setTimeLeft] = useState(session.time_remaining_seconds ?? 0);

  // Voice states
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
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

      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        setIsListening(true);
        setError("");
      };

      recognition.onresult = (event) => {
        let transcript = "";

        for (
          let i = event.resultIndex;
          i < event.results.length;
          i++
        ) {
          transcript +=
            event.results[i][0].transcript;
        }

        setAnswer(transcript);
      };

      recognition.onerror = (event) => {
        console.error(
          "Speech recognition error:",
          event.error
        );

        if (event.error !== "aborted") {
          setError(
            "Voice recognition failed. You can type your answer instead."
          );
        }

        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
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

      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      window.speechSynthesis.cancel();

      // Deliberately doesn't clear the speech watchdog or null speechDoneRef
      // here: this effect's cleanup also runs on React's dev-mode StrictMode
      // double-invoke (mount -> cleanup -> mount again) while the component
      // is still alive, and an in-flight speakQuestion() call (owned by the
      // other effect) must survive that round-trip intact.
    };
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

      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      window.speechSynthesis.cancel();

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
        window.speechSynthesis.cancel();

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

    if (speechSupported && "speechSynthesis" in window) {
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
  const finishSpeaking = (onDone) => {
    if (speechDoneRef.current !== onDone) {
      return;
    }

    speechDoneRef.current = null;

    if (speechWatchdogRef.current) {
      clearTimeout(speechWatchdogRef.current);
      speechWatchdogRef.current = null;
    }

    setIsSpeaking(false);

    if (onDone) onDone();
  };

  /*
   * Text-to-speech for interviewer. Browsers occasionally drop an
   * utterance silently - neither onend nor onerror fires - e.g. after tab
   * backgrounding, with certain voice-pack states, or if speak() is called
   * while the queue is paused. A watchdog timeout guarantees onDone always
   * runs, so the candidate is never stuck on AI_SPEAKING.
   */
  const speakQuestion = (question, onDone) => {
    if (
      !question ||
      !("speechSynthesis" in window)
    ) {
      if (onDone) onDone();
      return;
    }

    // A previous utterance's watchdog is now moot; its onDone has either
    // already run or is about to be superseded by this new call.
    if (speechWatchdogRef.current) {
      clearTimeout(speechWatchdogRef.current);
      speechWatchdogRef.current = null;
    }

    speechDoneRef.current = onDone;

    // speechSynthesis can get stuck reporting speaking/pending true from a
    // prior utterance; cancel() defensively before every speak() so the
    // browser reliably fires events for this one.
    window.speechSynthesis.cancel();

    const utterance =
      new SpeechSynthesisUtterance(question);

    utterance.rate = 0.95;
    utterance.pitch = 1;
    utterance.volume = 1;

    utterance.onstart = () => {
      setIsSpeaking(true);
    };

    utterance.onend = () => {
      finishSpeaking(onDone);
    };

    utterance.onerror = () => {
      finishSpeaking(onDone);
    };

    window.speechSynthesis.speak(
      utterance
    );

    const estimatedMs = Math.ceil(question.length / SPEECH_CHARS_PER_SEC) * 1000;

    const watchdogMs = Math.min(
      SPEECH_WATCHDOG_MAX_MS,
      Math.max(SPEECH_WATCHDOG_MIN_MS, estimatedMs + SPEECH_WATCHDOG_BUFFER_MS)
    );

    speechWatchdogRef.current = setTimeout(() => {
      console.warn(
        "speechSynthesis watchdog fired: neither onend nor onerror ran within",
        watchdogMs,
        "ms - forcing the interview to advance."
      );

      window.speechSynthesis.cancel();
      finishSpeaking(onDone);
    }, watchdogMs);
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
      recognitionRef.current.stop();
      setIsListening(false);
      return;
    }

    window.speechSynthesis.cancel();
    setIsSpeaking(false);

    setError("");

    try {
      recognitionRef.current.start();
    } catch (err) {
      console.error(
        "Could not start speech recognition:",
        err
      );
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

  /*
   * Submit candidate answer
   */
  const handleSubmit = async () => {
    if (
      !answer.trim() ||
      submitting ||
      timeLeft === 0 ||
      !canAnswer
    ) {
      return;
    }

    if (
      recognitionRef.current &&
      isListening
    ) {
      recognitionRef.current.stop();
    }

    window.speechSynthesis.cancel();

    setIsListening(false);
    setIsSpeaking(false);
    setError("");
    setSubmitting(true);

    try {
      await onSubmitAnswer(
        answer.trim(),
        averageAffectSamples(emotionSamplesRef.current)
      );

      setAnswer("");
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
   * Exit interview
   */
  const handleExit = () => {
    stopCamera();

    clearInterval(
      timerRef.current
    );

    clearInterval(
      faceDetectionIntervalRef.current
    );

    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }

    window.speechSynthesis.cancel();

    clearTimeout(speechWatchdogRef.current);
    speechDoneRef.current = null;

    setIsListening(false);
    setIsSpeaking(false);

    onExit();
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
            onClick={handleExit}
          >
            <LogOut size={16} />
            Exit Interview
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
          AI INTERVIEWER STAGE
          ========================= */}
      <div className="interview-stage">

        <div className="ai-avatar-block">
          <div className="ai-person-stage">
            <div className={`ai-person state-${avatarState}`}>
              <div className="ai-person-body">
                <div className="ai-person-lapel left" />
                <div className="ai-person-lapel right" />
                <div className="ai-person-collar" />
                <div className="ai-person-tie" />
              </div>

              <div className="ai-person-head">
                <div className="ai-person-hair" />
                <div className="ai-person-ear left" />
                <div className="ai-person-ear right" />

                <div className="ai-person-face">
                  <div className="ai-person-eyebrows">
                    <span />
                    <span />
                  </div>

                  <div className="ai-person-eyes">
                    <span className="ai-person-eye" />
                    <span className="ai-person-eye" />
                  </div>

                  <div className="ai-person-nose" />

                  <div className="ai-person-mouth-wrap">
                    <div className="ai-person-mouth" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="ai-avatar-status">
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
        </div>

        {/* CANDIDATE SELF-VIEW */}
        <div className="camera-pip">
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

      </div>

      {/* =========================
          ANSWER SECTION
          ========================= */}
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

    </div>
  );
}
