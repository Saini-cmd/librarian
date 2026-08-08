const stages = [
  { key: "ingest", label: "Ingesting repo" },
  { key: "scan", label: "Scanning files" },
  { key: "chunk", label: "Chunking code" },
  { key: "embed", label: "Embedding chunks" },
  { key: "ready", label: "Ready" },
];

export default function ProgressBar({ progress, statusText }) {
  const currentStageIdx = (() => {
    if (progress < 20) return 0;
    if (progress < 40) return 1;
    if (progress < 70) return 2;
    if (progress < 100) return 3;
    return 4;
  })();

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <p className="text-sm text-base-content/60 text-center">
        {statusText}
      </p>

      <progress
        className="progress progress-primary w-full"
        value={progress}
        max="100"
      />

      <ul className="steps steps-vertical lg:steps-horizontal w-full">
        {stages.map((stage, idx) => (
          <li
            key={stage.key}
            className={`step text-sm ${idx <= currentStageIdx ? "step-primary" : ""}`}
          >
            {stage.label}
          </li>
        ))}
      </ul>

      <p className="text-xs text-base-content/40 text-center">
        {Math.round(progress)}% complete
      </p>
    </div>
  );
}
