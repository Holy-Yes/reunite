const P: Record<string, string> = {
  home: "M4 11 12 4l8 7M6 10v10h12V10",
  match: "M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9",
  activity: "M4 6h16M4 12h16M4 18h10",
  bell: "M6 17V11a6 6 0 0 1 12 0v6l2 2H4zM10 21h4",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c1-4 4-6 8-6s7 2 8 6",
  desk: "M4 5h16v6H4zM4 15h7v4H4zM15 15h5v4h-5z",
  camera: "M4 8h4l2-3h4l2 3h4v11H4zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
  up: "M7 17 17 7M8 7h9v9",
  check: "M5 12l5 5 9-10",
  x: "M6 6l12 12M18 6 6 18",
  lock: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v9H5z",
  send: "M4 12 20 4l-4 16-4-7z",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4",
  plus: "M12 5v14M5 12h14",
  pin: "M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11zM12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
};
export function Icon({ n, size = 20, sw = 1.6 }: { n: keyof typeof P | string; size?: number; sw?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="square" strokeLinejoin="miter" aria-hidden="true">
      <path d={P[n] ?? P.image} />
    </svg>
  );
}
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="10" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <ellipse cx="16" cy="16" rx="14" ry="5" transform="rotate(-30 16 16)" fill="none" stroke="var(--orange)" strokeWidth="1.6" />
    </svg>
  );
}
