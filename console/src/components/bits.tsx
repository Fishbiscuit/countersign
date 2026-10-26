import { Check, Copy } from "lucide-react";
import { useState } from "react";
import type { IntentStatus } from "../lib/api";
import { CLIENT_COLORS, STATUS_LABEL, initials, statusTone } from "../lib/format";

export function StatusPill({ status }: { status: IntentStatus }) {
  const tone = statusTone(status);
  return (
    <span className={tone ? `badge badge-${tone}` : "badge"}>
      <span className="dot" />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Avatar({ name, client, size = 32 }: { name: string; client?: string | null; size?: number }) {
  return (
    <span
      className="avatar"
      style={{ background: CLIENT_COLORS[client ?? "other"] ?? CLIENT_COLORS.other, width: size, height: size, fontSize: size * 0.4 }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}

export function CopyField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="kbd-copy">
      <code aria-label={label}>{value}</code>
      <button
        className="btn btn-ghost"
        style={{ height: 30, padding: "0 10px" }}
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check size={15} /> : <Copy size={15} />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export function Countdown({ expiresAt, totalSeconds, now }: { expiresAt: string | null; totalSeconds: number; now: number }) {
  if (!expiresAt) return null;
  const remaining = Math.max(0, Math.round((new Date(expiresAt).getTime() - now) / 1000));
  const fraction = totalSeconds > 0 ? remaining / totalSeconds : 0;
  const circumference = 2 * Math.PI * 9;
  const label = remaining > 0 ? `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` : "expiring";
  return (
    <span className="countdown" title="The agent is waiting. If nobody decides in time, nothing is paid.">
      <svg className="ring" viewBox="0 0 22 22" aria-hidden="true">
        <circle className="track" cx="11" cy="11" r="9" />
        <circle
          className="bar"
          cx="11"
          cy="11"
          r="9"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - Math.min(1, fraction))}
        />
      </svg>
      <span className="num">{label}</span> agent waiting
    </span>
  );
}
