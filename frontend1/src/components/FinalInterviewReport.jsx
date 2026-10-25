import {
  CheckCircle2,
  ArrowLeft,
  Trophy,
  MessageSquareText,
  Brain,
  Target,
  Sparkles,
  ShieldCheck,
  Timer,
  BookOpen,
  Smile,
  Activity,
  Eye as EyeIcon,
  Layers,
} from "lucide-react";

export default function FinalInterviewReport({
  report,
  onBack,
}) {
  if (!report) {
    return (
      <div className="report-page">
        <div className="report-empty">
          <h2>No interview report available.</h2>

          <button
            className="report-back-button"
            onClick={onBack}
          >
            <ArrowLeft size={17} />
            Back to Interview
          </button>
        </div>
      </div>
    );
  }

  const getScoreClass = (score) => {
    if (score >= 80) return "score-excellent";
    if (score >= 60) return "score-good";
    return "score-needs-work";
  };

  const questionFeedback =
    report.question_feedback || [];

  return (
    <div className="report-page">
      <div className="report-container">

        <button
          className="report-back-button"
          onClick={onBack}
        >
          <ArrowLeft size={17} />
          Back to Interview
        </button>

        <div className="report-header">
          <div className="report-success-icon">
            <CheckCircle2 size={30} />
          </div>

          <div>
            <span className="interview-label">
              INTERVIEW COMPLETE
            </span>

            <h1>Final Interview Report</h1>

            <p>
              Here's how you performed during your
              interview.
            </p>
          </div>
        </div>

        {/* Overall Score */}
        <div className="overall-score-card">
          <div className="overall-score-left">
            <div className="trophy-icon">
              <Trophy size={25} />
            </div>

            <div>
              <span>Overall Score</span>

              <h2>
                {report.overall_score}
                <small>/100</small>
              </h2>
            </div>
          </div>

          <div
            className={`score-badge ${getScoreClass(
              report.overall_score
            )}`}
          >
            {report.overall_score >= 80
              ? "Excellent"
              : report.overall_score >= 60
              ? "Good"
              : "Needs Improvement"}
          </div>
        </div>

        {/* Performance Scores */}
        <div className="report-section">
          <h2>Performance Breakdown</h2>

          <div className="score-grid">

            <ScoreCard
              icon={<MessageSquareText size={20} />}
              label="Communication"
              score={report.communication}
            />

            <ScoreCard
              icon={<Brain size={20} />}
              label="Technical Knowledge"
              score={report.technical_knowledge}
            />

            <ScoreCard
              icon={<Target size={20} />}
              label="Answer Relevance"
              score={report.answer_relevance}
            />

            <ScoreCard
              icon={<MessageSquareText size={20} />}
              label="Clarity"
              score={report.clarity}
            />

            <ScoreCard
              icon={<Brain size={20} />}
              label="Problem Solving"
              score={report.problem_solving}
            />

          </div>
        </div>

        {/* Knowledge-Depth Analysis (Phase 7 MKT turns, Phase 10: surfaced
            per-concept rather than only folded into the overall score) */}
        {report.concept_belief_summary && report.concept_belief_summary.sample_count > 0 && (
          <div className="report-section">
            <h2>Knowledge-Depth Analysis</h2>

            <p className="report-section-note">
              Belief estimates for concepts probed with follow-up variations
              (paraphrase, constraint change, pushback, transfer), showing
              whether your understanding held up under those variations or
              was closer to memorised/surface recall.
            </p>

            <div className="score-grid">
              {report.concept_belief_summary.concepts.map((c) => (
                <ScoreCard
                  key={c.concept_id}
                  icon={<Layers size={20} />}
                  label={`${c.concept_name} (${c.classification})`}
                  score={formatPercent(c.robustness_index ?? c.mastery)}
                  max={null}
                />
              ))}
            </div>
          </div>
        )}

        {/* Communication Analysis (Phase 9: text + timing signals) */}
        {report.communication_summary && report.communication_summary.sample_count > 0 && (
          <div className="report-section">
            <h2>Communication Analysis</h2>

            <div className="score-grid">
              <ScoreCard
                icon={<Timer size={20} />}
                label="Avg Response Time"
                score={formatSeconds(report.communication_summary.avg_response_latency_seconds)}
                max={null}
              />

              <ScoreCard
                icon={<MessageSquareText size={20} />}
                label="Filler Word Rate"
                score={formatPercent(report.communication_summary.avg_filler_rate)}
                max={null}
              />

              <ScoreCard
                icon={<BookOpen size={20} />}
                label="Vocabulary Diversity"
                score={formatPercent(report.communication_summary.avg_vocabulary_diversity)}
                max={null}
              />
            </div>
          </div>
        )}

        {/* Presence & Engagement Signals (Phase 6 proctoring + Phase 9b
            emotion proxies, grouped as one "how present/engaged were you"
            narrative rather than two unrelated-looking blocks) */}
        {((report.proctoring_summary) ||
          (report.emotion_summary && report.emotion_summary.sample_count > 0)) && (
          <div className="report-section">
            <h2>Presence &amp; Engagement Signals</h2>

            {report.emotion_summary && report.emotion_summary.sample_count > 0 && (
              <p className="report-section-note">
                Heuristic proxies derived from facial expression intensity during
                your answers, not a clinical read of your emotional state.
              </p>
            )}

            <div className="score-grid">
              {report.proctoring_summary && (
                <>
                  <ScoreCard
                    icon={<ShieldCheck size={20} />}
                    label="Tab Switches"
                    score={report.proctoring_summary.tab_switch_count}
                    max={null}
                  />

                  <ScoreCard
                    icon={<ShieldCheck size={20} />}
                    label="Face Not Detected"
                    score={report.proctoring_summary.face_lost_count}
                    max={null}
                  />
                </>
              )}

              {report.emotion_summary && report.emotion_summary.sample_count > 0 && (
                <>
                  <ScoreCard
                    icon={<EyeIcon size={20} />}
                    label="Engagement"
                    score={formatPercent(report.emotion_summary.avg_engagement)}
                    max={null}
                  />

                  <ScoreCard
                    icon={<Activity size={20} />}
                    label="Stress Proxy"
                    score={formatPercent(report.emotion_summary.avg_stress_proxy)}
                    max={null}
                  />

                  <ScoreCard
                    icon={<Smile size={20} />}
                    label="Positive Expression"
                    score={formatPercent(report.emotion_summary.avg_positive_expression_proxy)}
                    max={null}
                  />
                </>
              )}
            </div>
          </div>
        )}

        {/* Strengths and Improvements */}
        <div className="report-two-column">

          <FeedbackCard
            title="Strengths"
            icon={<CheckCircle2 size={20} />}
            items={report.strengths || []}
          />

          <FeedbackCard
            title="Areas for Improvement"
            icon={<Target size={20} />}
            items={report.areas_for_improvement || []}
          />

        </div>

        {/* Question-wise Feedback */}
        <div className="report-section">
          <h2>Question-wise Feedback</h2>

          <div className="question-feedback-list">
            {questionFeedback.map((item, index) => (
              <div
                className="question-feedback-card"
                key={index}
              >
                <div className="feedback-question">
                  <span>
                    Question {index + 1}
                    {item.source === "mkt" && item.mkt_probe_type && (
                      <span className="question-mkt-tag">
                        {item.mkt_probe_type.replace("mr_", "").replace("_", " ")}
                      </span>
                    )}
                  </span>

                  <div className="question-score">
                    {item.score}/10
                  </div>
                </div>

                <p className="feedback-question-text">
                  {item.question}
                </p>

                <p className="feedback-evaluation">
                  {item.evaluation}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Final AI Feedback */}
        <div className="final-feedback-card">
          <div className="final-feedback-heading">
            <Sparkles size={21} />

            <h2>Final AI Feedback</h2>
          </div>

          <p>
            {report.final_feedback || "No final feedback was generated."}
          </p>
        </div>

        <button
          className="finish-report-button"
          onClick={onBack}
        >
          Return to Interview Setup
        </button>

      </div>
    </div>
  );
}


function formatSeconds(value) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(1)}s`;
}


function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}


function ScoreCard({
  icon,
  label,
  score = 0,
  max = 100,
}) {
  return (
    <div className="score-card">
      <div className="score-card-top">
        <div className="score-card-icon">
          {icon}
        </div>

        <span>{label}</span>
      </div>

      <div className="score-card-bottom">
        <strong>{score}</strong>
        {max !== null && <span>/{max}</span>}
      </div>

      {max !== null && (
        <div className="score-progress">
          <div
            className="score-progress-fill"
            style={{
              width: `${Math.max(
                0,
                Math.min(100, score)
              )}%`,
            }}
          />
        </div>
      )}
    </div>
  );
}


function FeedbackCard({
  title,
  icon,
  items,
}) {
  return (
    <div className="feedback-card">

      <div className="feedback-card-header">
        {icon}

        <h2>{title}</h2>
      </div>

      <div className="feedback-items">
        {items.length > 0 ? (
          items.map((item, index) => (
            <div
              className="feedback-item"
              key={index}
            >
              <span>•</span>
              <p>{item}</p>
            </div>
          ))
        ) : (
          <p className="no-feedback">
            No detailed feedback available.
          </p>
        )}
      </div>

    </div>
  );
}