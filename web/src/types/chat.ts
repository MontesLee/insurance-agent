/**
 * Chat contract (V0.1, local-only persistence — shaped so a future backend can
 * own the same objects verbatim). The chat NEVER owns agent execution state:
 * a run belongs to the runtime; the chat only references runId + renders
 * RuntimeEvents / artifacts produced by that run.
 */
import type { RunStatus } from "./runtime";

export type Message =
  | { kind: "user"; id: string; at: string; text: string }
  | { kind: "assistant"; id: string; at: string; text: string }
  | { kind: "activity"; id: string; at: string; runId: string; caseId: string }
  | {
      kind: "artifact";
      id: string;
      at: string;
      runId: string;
      artifactType: string;
      title: string;
    };

export interface ChatSession {
  id: string;
  title: string;
  caseId: string; // demo case this conversation maps to (Demo Mode)
  runId: string | null; // the runtime run this chat is currently observing
  /** Agent Mode: the server-side chat this conversation posts messages to */
  serverChatId?: string | null;
  mode?: "agent" | "demo";
  messages: Message[];
  createdAt: string;
  updatedAt: string;
}

/** localStorage envelope — versioned for future backend persistence. */
export interface ChatStore {
  version: 1;
  chats: ChatSession[];
}

export interface ConflictInfo {
  caseId: string;
  runId: string;
  ownerChatId: string | null;
}

export type TerminalKind = RunStatus;
