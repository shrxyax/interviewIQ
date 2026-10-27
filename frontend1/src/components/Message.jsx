import ReactMarkdown from "react-markdown";

export default function Message({ message }) {
  const isUser = message.role === "user";

  return (
    <div className={`message ${isUser ? "user" : "assistant"}`}>

      <div className="message-bubble">

        <ReactMarkdown>
          {message.content}
        </ReactMarkdown>

      </div>

    </div>
  );
}
