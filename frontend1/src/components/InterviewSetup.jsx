import { useState } from "react";
import {
  ArrowLeft,
  BriefcaseBusiness,
  Code2,
  ListChecks,
  BookOpen,
  Workflow,
  Shuffle,
  SlidersHorizontal,
  Play,
} from "lucide-react";
import "./Interview.css";

const INTERVIEW_TYPES = [
  { value: "hr", label: "HR Interview", icon: BriefcaseBusiness, description: "Behavioural, communication, teamwork, leadership and career-focused questions." },
  { value: "technical", label: "Technical", icon: Code2, description: "Projects, programming, technologies and fundamentals from your resume." },
  { value: "dsa", label: "DSA", icon: ListChecks, description: "Data structures and algorithms, probed for robust rather than memorised understanding." },
  { value: "core_cs", label: "Core CS", icon: BookOpen, description: "OS, DBMS, networks and other core computer science fundamentals." },
  { value: "system_design", label: "System Design", icon: Workflow, description: "Architecture trade-offs, scalability and failure handling." },
  { value: "mixed", label: "Mixed", icon: Shuffle, description: "A blend of technical, DSA and behavioural questions." },
  { value: "custom", label: "Custom", icon: SlidersHorizontal, description: "An interview shaped mostly by your resume and target role." },
];

const EXPERIENCE_LEVELS = [
  { value: "intern", label: "Intern" },
  { value: "junior", label: "Junior (0-2 yrs)" },
  { value: "mid", label: "Mid (2-5 yrs)" },
  { value: "senior", label: "Senior (5+ yrs)" },
];

const DURATIONS = [15, 30, 45, 60];
const QUESTION_COUNTS = [5, 8, 10, 15];

export default function InterviewSetup({
  onStart,
  onBack,
  loading = false,
}) {
  const [targetRole, setTargetRole] = useState("");
  const [company, setCompany] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("junior");
  const [interviewType, setInterviewType] = useState("technical");
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [numQuestions, setNumQuestions] = useState(8);

  const canStart = targetRole.trim().length >= 2;

  const handleStart = () => {
    if (!canStart) return;

    onStart({
      target_role: targetRole.trim(),
      company: company.trim() || null,
      experience_level: experienceLevel,
      interview_type: interviewType,
      duration_minutes: Number(durationMinutes),
      num_questions: numQuestions === "unlimited" ? null : Number(numQuestions),
    });
  };

  return (
    <div className="interview-page">
      <div className="interview-setup">
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={17} />
          Back
        </button>

        <div className="interview-setup-header">
          <span className="interview-label">AI INTERVIEW</span>
          <h1>Prepare for your interview</h1>
          <p>
            Tell us what you're interviewing for. Your uploaded resume is used
            automatically to personalize the questions.
          </p>
        </div>

        <div className="setup-section">
          <h3>Role</h3>

          <div className="setup-row">
            <input
              className="setup-text-input"
              type="text"
              placeholder="Target role (e.g. Frontend Engineer)"
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
            />

            <input
              className="setup-text-input"
              type="text"
              placeholder="Company (optional)"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </div>
        </div>

        <div className="setup-section">
          <h3>Experience Level</h3>

          <select
            className="question-select"
            value={experienceLevel}
            onChange={(e) => setExperienceLevel(e.target.value)}
          >
            {EXPERIENCE_LEVELS.map((level) => (
              <option key={level.value} value={level.value}>
                {level.label}
              </option>
            ))}
          </select>
        </div>

        <div className="setup-section">
          <h3>Interview Type</h3>

          <div className="interview-type-grid">
            {INTERVIEW_TYPES.map((type) => (
              <button
                key={type.value}
                className={`interview-type-card ${
                  interviewType === type.value ? "selected" : ""
                }`}
                onClick={() => setInterviewType(type.value)}
              >
                <div className="type-icon">
                  <type.icon size={24} />
                </div>

                <div>
                  <h4>{type.label}</h4>
                  <p>{type.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="setup-section">
          <h3>Duration</h3>

          <select
            className="question-select"
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(Number(e.target.value))}
          >
            {DURATIONS.map((minutes) => (
              <option key={minutes} value={minutes}>
                {minutes} minutes
              </option>
            ))}
          </select>
        </div>

        <div className="setup-section">
          <h3>Number of Questions</h3>

          <select
            className="question-select"
            value={numQuestions}
            onChange={(e) =>
              setNumQuestions(
                e.target.value === "unlimited" ? "unlimited" : Number(e.target.value)
              )
            }
          >
            {QUESTION_COUNTS.map((count) => (
              <option key={count} value={count}>
                {count} questions
              </option>
            ))}
            <option value="unlimited">No limit (time only)</option>
          </select>
        </div>

        <button
          className="start-interview-button"
          onClick={handleStart}
          disabled={loading || !canStart}
        >
          <Play size={18} />
          {loading ? "Starting Interview..." : "Start Interview"}
        </button>
      </div>
    </div>
  );
}
