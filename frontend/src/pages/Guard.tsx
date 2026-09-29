import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { api, ApiError } from "../api";
import { useT } from "../i18n";
import { Field } from "../components/bits";

/** Handover confirmation only: scan the owner's QR pass, or fall back to the six-digit code.
 * No claims queue, no bulk logging -- see the "desk" role for those. */
export default function Guard() {
  const { t } = useT();
  const [code, setCode] = useState("");
  const [idOk, setIdOk] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const idOkRef = useRef(idOk);
  idOkRef.current = idOk;

  function stopScan() {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
    setScanning(false);
  }
  useEffect(() => stopScan, []);

  async function confirm(b: { code?: string; token?: string }) {
    setMsg(null);
    try {
      const r = await api.confirmHandover({ ...b, id_checked: idOkRef.current });
      setMsg({ ok: true, text: `${t("desk.confirmBtn")}: ${r.item.ticket_no}` });
      setCode("");
      setIdOk(false);
      stopScan();
    } catch (x) {
      setMsg({ ok: false, text: (x as ApiError).message });
    }
  }

  function tick() {
    const video = videoRef.current, canvas = canvasRef.current;
    if (video && canvas && video.readyState === video.HAVE_ENOUGH_DATA) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const frame = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const decoded = jsQR(frame.data, frame.width, frame.height);
        if (decoded?.data) { void confirm({ token: decoded.data }); return; }
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  }

  async function startScan() {
    setScanError(null);
    if (!navigator.mediaDevices?.getUserMedia) { setScanError(t("guard.scanUnsupported")); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play(); }
      setScanning(true);
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      setScanError(t("guard.scanUnsupported"));
    }
  }

  return (
    <main className="page stack--lg stack" id="main">
      <h1 className="h2">{t("guard.title")}</h1>
      <div className="stack" style={{ maxWidth: 420 }}>
        {scanning ? (
          <>
            <p className="muted">{t("guard.scanHint")}</p>
            <video ref={videoRef} muted playsInline style={{ width: "100%", borderRadius: 12 }} />
            <button className="btn" onClick={stopScan}>{t("common.cancel")}</button>
          </>
        ) : (
          <button className="btn btn--ink" onClick={startScan}>{t("guard.scanBtn")}</button>
        )}
        <canvas ref={canvasRef} style={{ display: "none" }} aria-hidden />
        {scanError && <p className="banner banner--bad" role="status">{scanError}</p>}
        <p className="muted">{t("guard.orCode")}</p>
        <Field label={t("desk.code")}><input className="input input--code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
        <label className="row"><input type="checkbox" checked={idOk} onChange={(e) => setIdOk(e.target.checked)} /> {t("desk.idChecked")}</label>
        {msg && <p className={msg.ok ? "banner banner--ok" : "banner banner--bad"} role="status">{msg.text}</p>}
        <button className="btn btn--ink" disabled={code.length !== 6} onClick={() => confirm({ code })}>{t("desk.confirmBtn")}</button>
      </div>
    </main>
  );
}
