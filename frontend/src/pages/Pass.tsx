import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import QRCode from "qrcode";
import { api } from "../api";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { useAsync } from "../lib";
import { useRef_ } from "../ref";
import { ErrorBox, Loading } from "../components/bits";

export default function Pass() {
  const { id = "" } = useParams();
  const { t } = useT();
  const { zoneName } = useRef_();
  const ho = useAsync(() => api.handover(id), [id]);
  const claim = useAsync(() => api.claim(id), [id]);
  const canvas = useRef<HTMLCanvasElement>(null);
  const h = ho.data;

  useEffect(() => { if (h && canvas.current && !h.expired) void QRCode.toCanvas(canvas.current, h.qr_payload, { width: 280, margin: 1 }); }, [h]);
  useEffect(() => {
    const i = setInterval(() => void claim.reload(), 8000);
    return () => clearInterval(i);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (claim.data?.status === "handed_over") {
    return <main className="page stack" id="main"><h1 className="h1"><Icon n="check" size={48} sw={2} /></h1><Link className="btn btn--ink" to={`/claims/${id}`}>{t("tip.title")}</Link></main>;
  }
  return (
    <main className="page stack--lg stack" id="main">
      <h1 className="h2">{t("pass.title")}</h1>
      {ho.loading && !h ? <Loading /> : ho.error ? <ErrorBox error={ho.error} retry={ho.reload} /> : h && (
        <div className="pass">
          {h.expired ? (
            <>
              <p className="banner banner--bad">{t("pass.expired")}</p>
              <button className="btn btn--lost" onClick={async () => ho.setData(await api.newHandover(id))}>{t("pass.renew")}</button>
            </>
          ) : (
            <>
              <p className="muted">{t("pass.show")}</p>
              <canvas ref={canvas} aria-label="QR code" />
              <p className="muted">{t("pass.code")}</p>
              <p className="pass__code" aria-label={h.code.split("").join(" ")}>{h.code}</p>
              <p className="muted">{t("pass.collect")} <strong>{zoneName(h.collect_zone_id)}</strong></p>
            </>
          )}
        </div>
      )}
    </main>
  );
}
