import { useState } from "react";

export default function ChatInput({ onSend }) {
  const [question, setQuestion] = useState("");

  const handleSend = () => {
    if (!question.trim()) return;

    onSend(question);

    setQuestion("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleSend();
    }
  };

  return (
    <div className="chat-input-container">

      <input
        className="chat-input"
        placeholder="Ask about your resume, a CS concept, or interview prep..."
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
      />

      <button
        className="send-btn"
        onClick={handleSend}
      >
        Send
      </button>

    </div>
  );
}