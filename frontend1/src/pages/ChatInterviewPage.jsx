import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { FileText, Upload, Video } from "lucide-react";

import UploadBox from "../components/UploadBox";
import ChatBox from "../components/ChatBox";
import ChatInput from "../components/ChatInput";
import InterviewSetup from "../components/InterviewSetup";
import InterviewScreen from "../components/InterviewScreen";
import FinalInterviewReport from "../components/FinalInterviewReport";

import api from "../services/api";
import {
  createInterviewContext,
  getInterviewContext,
  getInterviewSession,
  markListening,
  reportProctoringEvent,
  startInterviewSession,
  submitInterviewAnswer as submitInterviewAnswerRequest,
} from "../services/interviewContext";

// Survives a page refresh mid-interview: the backend session is the
// source of truth, this just remembers which one to re-fetch.
const ACTIVE_SESSION_KEY = "iq_active_interview_session_id";

export default function ChatInterviewPage() {
  const location = useLocation();

  const [uploaded, setUploaded] = useState(false);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const [currentView, setCurrentView] = useState("chat");

  const [interviewSession, setInterviewSession] = useState(null);
  const [interviewContextInfo, setInterviewContextInfo] = useState(null);
  const [interviewReport, setInterviewReport] = useState(null);
  const [fileName, setFileName] = useState("");
  const [resumeId, setResumeId] = useState(null);

  // Sidebar's "New Chat" / "AI Interview" buttons navigate here with a
  // location.state flag (since the sidebar is shared across every route
  // now, it can't call these handlers directly).
  useEffect(() => {
    if (location.state?.action === "new") {
      newChat();
    } else if (location.state?.action === "interview") {
      openInterview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // Resume a mid-interview session after a page refresh.
  useEffect(() => {
    const savedSessionId = localStorage.getItem(ACTIVE_SESSION_KEY);
    if (!savedSessionId) return;

    getInterviewSession(savedSessionId)
      .then((session) => {
        setUploaded(true);
        applySessionUpdate(session);
      })
      .catch(() => {
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applySessionUpdate = async (session, contextInfo) => {
    if (session.state === "REPORT") {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      setInterviewReport(session.report);
      setInterviewSession(null);
      setCurrentView("report");
      return;
    }

    const resolvedContext =
      contextInfo || interviewContextInfo || (await getInterviewContext(session.context_id));

    localStorage.setItem(ACTIVE_SESSION_KEY, session.session_id);
    setInterviewContextInfo(resolvedContext);
    setInterviewSession(session);
    setCurrentView("interview");
  };

  const handleUpload = async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await api.post("/upload", formData);

      console.log(res.data);

      setUploaded(true);
      setFileName(file.name);
      setResumeId(res.data.resume_id ?? null);
      setCurrentView("chat");

      setInterviewSession(null);
      setInterviewReport(null);

      setMessages([
        {
          role: "assistant",
          content:
            "Document uploaded successfully.\n\nAsk me anything about your document.",
          sources: [],
        },
      ]);
    } catch (err) {
      console.error(err);
      alert("Upload failed.");
    }
  };

  const sendMessage = async (question) => {
    if (!question.trim()) return;

    if (!uploaded) {
      setMessages([
        {
          role: "assistant",
          content: "Please upload a PDF before asking questions.",
          sources: [],
        },
      ]);
      return;
    }

    const userMessage = {
      role: "user",
      content: question,
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const res = await api.post("/chat", {
        question,
      });

      const assistantMessage = {
        role: "assistant",
        content: res.data.answer,
        sources: res.data.sources || [],
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      console.error(err);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Something went wrong.",
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    setCurrentView("chat");
    setInterviewSession(null);
    setInterviewReport(null);

    setMessages([
      {
        role: "assistant",
        content:
          "Started a new conversation. Ask anything about your uploaded document.",
        sources: [],
      },
    ]);
  };

  const openInterview = () => {
    if (!uploaded) {
      alert("Please upload your resume before starting an interview.");
      return;
    }

    setCurrentView("interview-setup");
  };

  const exitInterview = () => {
    // The backend session is left as-is (it'll just time out); only the
    // "which session to resume" pointer is cleared.
    localStorage.removeItem(ACTIVE_SESSION_KEY);
    setInterviewSession(null);
    setCurrentView("chat");
  };

  const handleInterviewTimeExpired = async () => {
    if (!interviewSession) return;

    try {
      const session = await getInterviewSession(interviewSession.session_id);
      await applySessionUpdate(session);
    } catch (err) {
      console.error("Failed to resync expired interview session:", err);
      localStorage.removeItem(ACTIVE_SESSION_KEY);
      setInterviewSession(null);
      setCurrentView("interview-setup");
    }
  };

  const startInterview = async ({
    target_role,
    company,
    experience_level,
    interview_type,
    duration_minutes,
    num_questions,
  }) => {
    setLoading(true);

    try {
      const context = await createInterviewContext({
        target_role,
        company,
        experience_level,
        interview_type,
        duration_minutes,
        num_questions,
        resume_id: resumeId,
      });

      const session = await startInterviewSession(context.context_id);

      setInterviewReport(null);
      await applySessionUpdate(session, context);
    } catch (err) {
      console.error(err);

      alert(
        err.response?.data?.detail ||
          "Failed to start the interview."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReadyForAnswer = async () => {
    if (!interviewSession) return;

    try {
      const session = await markListening(interviewSession.session_id);
      await applySessionUpdate(session);
    } catch (err) {
      console.error("Failed to move interview into listening state:", err);
    }
  };

  // Best-effort: a dropped proctoring event is not worth retrying or
  // surfacing to the candidate, it just means the report's summary undercounts.
  const handleProctoringEvent = (eventType) => {
    if (!interviewSession) return;

    reportProctoringEvent(interviewSession.session_id, eventType).catch((err) => {
      console.error("Failed to report proctoring event:", err);
    });
  };

  // Resyncs local state against the backend's authoritative clock/state,
  // so a throttled background tab can't leave the candidate staring at a
  // countdown that no longer matches what the server has already decided.
  const handleSyncInterviewSession = async () => {
    if (!interviewSession) return;

    try {
      const session = await getInterviewSession(interviewSession.session_id);
      await applySessionUpdate(session);
    } catch (err) {
      console.error("Failed to sync interview session:", err);
    }
  };

  const handleSubmitInterviewAnswer = async (answer, emotionSignal) => {
    if (!interviewSession) {
      throw new Error("Interview session not found.");
    }

    try {
      const session = await submitInterviewAnswerRequest(interviewSession.session_id, answer, emotionSignal);
      await applySessionUpdate(session);
    } catch (err) {
      console.error(
        "Interview answer submission failed:",
        err
      );

      throw err;
    }
  };

  return (
    <main className="main-content">

      {/* Upload Screen */}
      {!uploaded && (
        <>
          <div className="hero">
            <h1>InterviewIQ</h1>
            <p>Your AI Interview Preparation Assistant</p>

            <UploadBox onUpload={handleUpload} />
          </div>

          <ChatInput onSend={sendMessage} />
        </>
      )}

      {/* Normal Chat */}
      {uploaded && currentView === "chat" && (
        <>
          <div className="chat-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <h2>InterviewIQ</h2>
              <p>
                Ask anything about your uploaded document.
              </p>
            </div>

            <div
              style={{
                display: "flex", alignItems: "center", gap: 10,
                background: "var(--card)", border: "1px solid var(--border)",
                borderRadius: 12, padding: "8px 14px", fontSize: 13, color: "var(--muted)",
              }}
            >
              <FileText size={15} />
              <span style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {fileName || "document.pdf"}
              </span>
              <button
                onClick={() => { setUploaded(false); setCurrentView("chat"); setInterviewSession(null); setInterviewReport(null); }}
                title="Upload another PDF"
                style={{ background: "transparent", border: "none", color: "var(--muted)", display: "flex", padding: 0 }}
              >
                <Upload size={15} />
              </button>
              <button
                onClick={openInterview}
                title="Start AI interview on this resume"
                style={{ background: "transparent", border: "none", color: "var(--primary)", display: "flex", padding: 0 }}
              >
                <Video size={15} />
              </button>
            </div>
          </div>

          <div className="chat-container">
            <ChatBox
              messages={messages}
              loading={loading}
            />
          </div>

          <ChatInput onSend={sendMessage} />
        </>
      )}

      {/* Interview Setup */}
      {uploaded &&
        currentView === "interview-setup" && (
          <InterviewSetup
            onStart={startInterview}
            onBack={exitInterview}
            loading={loading}
          />
        )}

      {/* Live Interview */}
      {uploaded &&
        currentView === "interview" &&
        interviewSession && (
          <InterviewScreen
            session={{ ...interviewSession, context: interviewContextInfo }}
            onExit={exitInterview}
            onReadyForAnswer={handleReadyForAnswer}
            onSubmitAnswer={handleSubmitInterviewAnswer}
            onTimeExpired={handleInterviewTimeExpired}
            onProctoringEvent={handleProctoringEvent}
            onSync={handleSyncInterviewSession}
          />
        )}

      {/* Final Report */}
      {uploaded && currentView === "report" && (
        <FinalInterviewReport
          report={interviewReport}
          onBack={() => {
            setInterviewReport(null);
            setCurrentView("interview-setup");
          }}
        />
      )}

    </main>
  );
}
