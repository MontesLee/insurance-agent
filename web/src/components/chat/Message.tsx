import type { Message as Msg } from "../../types/chat";
import { Markdown } from "../Markdown";

/** One chat message. Activity and artifact kinds have their own cards. */
export function MessageView({ message }: { message: Msg }) {
  if (message.kind === "user") {
    return (
      <div className="flex justify-end" data-testid="msg-user">
        <div className="max-w-[75%] rounded-2xl rounded-br-md bg-slate-800 px-4 py-2.5 text-[13.5px] leading-relaxed text-white">
          {message.text}
        </div>
      </div>
    );
  }
  if (message.kind === "assistant") {
    return (
      <div className="flex justify-start" data-testid="msg-assistant">
        <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-2.5 shadow-sm">
          <Markdown text={message.text} />
        </div>
      </div>
    );
  }
  return null; // activity/artifact are rendered by the conversation (need stream state)
}
