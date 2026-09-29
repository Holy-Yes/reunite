export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <symbol id="i-up-right" viewBox="0 0 24 24"><path d="M7 17 17 7M8 7h9v9" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" /></symbol>
      <symbol id="i-down" viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" /></symbol>
      <symbol id="i-left" viewBox="0 0 24 24"><path d="M19 12H5M11 6l-6 6 6 6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" /></symbol>
      <symbol id="i-star" viewBox="0 0 24 24"><path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="butt" /></symbol>
    </svg>
  );
}

export function Icon({ name, size = 16 }: { name: "up-right" | "down" | "left" | "star" | "orbit"; size?: number }) {
  return <svg width={size} height={size} aria-hidden="true"><use href={`#i-${name}`} /></svg>;
}
