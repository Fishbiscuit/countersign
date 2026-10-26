/** The moment of decision: a signature is drawn on the line, then a seal lands on the card. */

const SIGNATURE =
  "M8 96 C 30 30, 62 18, 74 66 S 104 132, 128 74 S 158 14, 182 72 S 214 120, 236 70 S 262 30, 284 64 " +
  "C 296 84, 304 98, 322 80 S 352 34, 372 58 S 398 104, 424 76 C 444 54, 470 44, 500 60 S 548 86, 590 52";

export function SignatureLine({ approved, caption }: { approved: boolean; caption: string }) {
  return (
    <div className={`sign-line ${approved ? "" : "denied"}`}>
      <svg className="signature" viewBox="0 0 600 140" preserveAspectRatio="none" aria-hidden="true">
        <path d={SIGNATURE} />
      </svg>
      <div className="sign-caption">{caption}</div>
    </div>
  );
}

export function Seal({ approved }: { approved: boolean }) {
  const word = approved ? "COUNTERSIGNED" : "DENIED";
  const color = approved ? "var(--accent)" : "var(--seal)";
  const ring = approved ? `${word} · ${word} · ` : `${word} · ${word} · ${word} · `;
  return (
    <svg className="seal" viewBox="0 0 128 128" aria-hidden="true">
      <defs>
        <path id={`ring-${word}`} d="M64 64 m -46 0 a 46 46 0 1 1 92 0 a 46 46 0 1 1 -92 0" />
      </defs>
      <circle cx="64" cy="64" r="60" fill={color} opacity="0.94" />
      <circle cx="64" cy="64" r="53" fill="none" stroke="#fff" strokeOpacity="0.7" strokeWidth="1.2" />
      <circle cx="64" cy="64" r="33" fill="none" stroke="#fff" strokeOpacity="0.7" strokeWidth="1.2" strokeDasharray="2 3" />
      <text fill="#fff">
        <textPath href={`#ring-${word}`} textLength="282">
          {ring}
        </textPath>
      </text>
      {approved ? (
        <path d="M48 65 l11 11 l22 -24" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <path d="M51 51 l26 26 M77 51 l-26 26" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
      )}
    </svg>
  );
}

export function SealMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="29" fill="var(--seal)" />
      <circle cx="32" cy="32" r="23" fill="none" stroke="#fff6ee" strokeWidth="2" strokeDasharray="2 3" />
      <path
        d="M17 38c5-9 8-14 11-14 3 0 1 9 4 9s5-7 8-7 3 5 7 4"
        fill="none"
        stroke="#fff6ee"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
