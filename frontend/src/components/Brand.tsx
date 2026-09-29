import { useId } from "react";

/**
 * The reunite mark: a circle (the campus) with an orange orbit around it and a dot, the item on its way back.
 * The far half of the orbit goes behind the circle, the near half in front. Colours follow the theme: the circle
 * takes the current text colour, the orbit is always orange.
 */
export function LogoMark({ size = 30 }: { size?: number }) {
  const id = useId();
  return (
    <svg className="brand__mark" width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <defs>
        {/* hides the part of the far arc that is inside the circle, so it reads as passing behind */}
        <mask id={`${id}-m`} maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
          <rect width="64" height="64" fill="#fff" />
          <circle cx="32" cy="32" r="20" fill="#000" />
        </mask>
      </defs>
      <circle cx="32" cy="32" r="20" stroke="currentColor" strokeWidth="3.4" />
      <g transform="translate(32 32) rotate(-28)" stroke="#FF6A13" strokeWidth="3.4" strokeLinecap="round">
        <path d="M-30 0A30 12 0 0 1 30 0" mask={`url(#${id}-m)`} />
        <path d="M-30 0A30 12 0 0 0 30 0" />
        <circle cx="17" cy="9.9" r="4.6" fill="#FF6A13" stroke="none" />
      </g>
    </svg>
  );
}

/** Mark and lowercase wordmark with the orange full stop. Put it inside a link with the `brand` class. */
export default function Brand({ size = 30 }: { size?: number }) {
  return (
    <>
      <LogoMark size={size} />
      <span className="brand__word">reunite<i>.</i></span>
    </>
  );
}
