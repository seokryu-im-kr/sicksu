declare class Html5Qrcode {
  constructor(elementId: string);
  start(
    cameraIdOrConfig: { facingMode: string } | string,
    config: {
      fps: number;
      qrbox: { width: number; height: number };
      aspectRatio?: number;
    },
    onSuccess: (decodedText: string) => void,
    onError: (error: string) => void
  ): Promise<void>;
  stop(): Promise<void>;
  getRunningTrackCameraCapabilities(): unknown;
}

declare namespace Html5Qrcode {
  function getCameras(): Promise<Array<{ id: string; label: string }>>;
}

declare const lucide: { createIcons: () => void };

type CheckinStatus = "success" | "fail" | "duplicate";

interface CheckinResponse {
  status: CheckinStatus;
  message: string;
}

let scanner: Html5Qrcode | null = null;
let isProcessing = false;
let resultTimer: ReturnType<typeof setTimeout> | null = null;
let useFrontCamera = false;
let cameraList: Array<{ id: string; label: string }> = [];

const RESULT_DURATION = 3000;
const COOLDOWN_AFTER_HIDE = 500;

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function setStatus(text: string, error = false): void {
  const el = $("status-text");
  const dot = $("status-dot");
  const info = $("status-info");
  if (el) el.textContent = text;
  if (error && dot) {
    dot.classList.replace("bg-blue-500", "bg-red-500");
    dot.classList.remove("animate-ping");
  }
  if (error && info) info.classList.add("bg-red-50", "border-red-100");
}

async function initScanner(): Promise<void> {
  try {
    cameraList = await Html5Qrcode.getCameras();
  } catch {
    cameraList = [];
  }

  // Show switch button if multiple cameras
  const switchBtn = $("camera-switch-btn");
  if (switchBtn && cameraList.length > 1) {
    switchBtn.classList.remove("hidden");
  }

  scanner = new Html5Qrcode("qr-reader");
  startCamera();
}

function startCamera(): void {
  if (!scanner) return;

  const facingMode = useFrontCamera ? "user" : "environment";

  scanner
    .start(
      { facingMode },
      {
        fps: 10,
        qrbox: { width: 250, height: 250 },
      },
      onScanSuccess,
      () => {}
    )
    .then(() => {
      setStatus(
        useFrontCamera ? "전면 카메라 활성: 스캔 대기 중" : "후면 카메라 활성: 스캔 대기 중"
      );
    })
    .catch((err: string) => {
      setStatus("카메라 실패: " + err, true);
    });
}

function onScanSuccess(decodedText: string): void {
  if (isProcessing) return;
  isProcessing = true;

  if (navigator.vibrate) navigator.vibrate(200);

  setStatus("스캔 완료 — 서버 확인 중...");
  sendCheckin(decodedText);
}

async function sendCheckin(qrData: string): Promise<void> {
  try {
    const r = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ qr_data: qrData }),
    });
    const data: CheckinResponse = await r.json();
    showResult(data.status, data.message);
  } catch {
    showResult("fail", "서버 통신에 실패했습니다.");
  }
}

function showResult(status: CheckinStatus, message: string): void {
  const area = $("result-area");
  const card = $("result-card");
  const icon = $("result-icon");
  const msg = $("result-message");

  if (!area || !card || !icon || !msg) return;

  if (resultTimer) clearTimeout(resultTimer);

  msg.textContent = message;

  const base = "flex items-center gap-3 px-5 py-4 rounded-2xl shadow-lg";

  if (status === "success") {
    card.className = base + " bg-emerald-500";
    icon.setAttribute("data-lucide", "check-circle-2");
  } else if (status === "duplicate") {
    card.className = base + " bg-amber-500";
    icon.setAttribute("data-lucide", "alert-triangle");
  } else {
    card.className = base + " bg-red-500";
    icon.setAttribute("data-lucide", "x-circle");
  }
  msg.className = "text-sm sm:text-base font-bold leading-tight text-white";
  icon.className = "w-7 h-7 text-white shrink-0";

  lucide.createIcons();

  area.classList.remove("hidden");

  resultTimer = setTimeout(function () {
    area.classList.add("hidden");
    setStatus(
      useFrontCamera ? "전면 카메라 활성: 스캔 대기 중" : "후면 카메라 활성: 스캔 대기 중"
    );
    isProcessing = false;
  }, RESULT_DURATION);
}

// Exposed globally for onclick
(window as unknown as Record<string, () => void>).switchCamera =
  function switchCamera(): void {
    if (!scanner) return;
    scanner
      .stop()
      .then(() => {
        useFrontCamera = !useFrontCamera;
        startCamera();
      })
      .catch(() => {
        useFrontCamera = !useFrontCamera;
        startCamera();
      });
  };

initScanner();
