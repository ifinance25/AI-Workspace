import { AUTH_UNAUTHORIZED_EVENT } from "@/api/client";
import { BASE_WITH_SLASH } from "@/api/base";

const WS_POLICY_VIOLATION = 1008;

export interface SshWsHandle {
  send: (msg: object) => void;
  close: () => void;
}

export type SshWsFrame =
  | { type: "ready"; host: string; port: number; username: string }
  | { type: "out"; data: string }
  | { type: "error"; error: string };

export function openSshWs(
  onMessage: (msg: SshWsFrame) => void,
  opts: { onClose?: (code: number) => void } = {},
): SshWsHandle {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(
    `${proto}//${window.location.host}${BASE_WITH_SLASH}api/ws/ssh`,
  );
  let closedByUser = false;

  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data) as SshWsFrame);
    } catch {
      /* ignore malformed frames */
    }
  };
  ws.onclose = (e) => {
    opts.onClose?.(e.code);
    if (closedByUser) return;
    if (e.code === WS_POLICY_VIOLATION && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
  };

  return {
    send: (msg) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
      }
    },
    close: () => {
      closedByUser = true;
      ws.close();
    },
  };
}
