// Illustrated interviewer face for the live interview room. All motion
// (blink, lip-sync, head tilt, eye glance) is driven by CSS from the
// `state` class: idle | speaking | listening | thinking.
export default function InterviewerFace({ state }) {
  return (
    <div className={`ai-avatar state-${state}`} aria-hidden="true">
      <span className="ai-avatar-ring" />
      <span className="ai-avatar-ring" />
      <span className="ai-avatar-ring" />
      <span className="ai-avatar-arc" />

      <div className="ai-face">
        <svg viewBox="22 24 156 156" className="ai-face-svg">
          <g className="ai-face-head">
            {/* neck */}
            <path d="M84 140 h32 v44 q-16 8 -32 0 z" className="skin-shade" />

            {/* ears */}
            <ellipse cx="53" cy="102" rx="9" ry="14" className="skin" />
            <ellipse cx="147" cy="102" rx="9" ry="14" className="skin" />

            {/* face */}
            <ellipse cx="100" cy="98" rx="47" ry="57" className="skin" />

            {/* hair */}
            <path
              d="M52 96 C48 48 78 30 101 30 C128 30 154 46 149 96
                 C145 74 131 60 111 58 C95 56 79 62 67 72 C59 79 54 87 52 96 Z"
              className="hair"
            />

            {/* cheeks */}
            <circle cx="72" cy="118" r="8" className="cheek" />
            <circle cx="128" cy="118" r="8" className="cheek" />

            {/* eyebrows */}
            <g className="ai-face-brows">
              <path d="M69 82 Q80 75 91 81" className="brow" />
              <path d="M109 81 Q120 75 131 82" className="brow" />
            </g>

            {/* eyes */}
            <g className="ai-face-eyes">
              <g className="ai-face-eye">
                <ellipse cx="80" cy="99" rx="8.5" ry="6" className="eye-white" />
                <g className="ai-face-iris">
                  <circle cx="80" cy="99" r="3.8" className="iris" />
                  <circle cx="81.3" cy="97.7" r="1.2" className="eye-glint" />
                </g>
              </g>
              <g className="ai-face-eye">
                <ellipse cx="120" cy="99" rx="8.5" ry="6" className="eye-white" />
                <g className="ai-face-iris">
                  <circle cx="120" cy="99" r="3.8" className="iris" />
                  <circle cx="121.3" cy="97.7" r="1.2" className="eye-glint" />
                </g>
              </g>
            </g>

            {/* nose */}
            <path d="M100 103 Q95 116 99 119 Q102 120 105 118" className="nose" />

            {/* mouth: a closed smile, swapped for an open mouth while speaking */}
            <path d="M87 132 Q100 141 113 132" className="mouth-closed" />
            <ellipse cx="100" cy="135" rx="10" ry="6.5" className="mouth-open" />
          </g>
        </svg>
      </div>
    </div>
  );
}
