function formatResetTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function QuotaNotice({ quota, onDismiss }) {
  if (!quota) return null;

  const isIngest = quota.group === "ingest";
  const unit = isIngest ? "ingests" : "messages";
  const used = typeof quota.used === "number" ? quota.used : 0;
  const limit = typeof quota.limit === "number" ? quota.limit : 0;
  const resetTime = formatResetTime(quota.resets_at);

  return (
    <div role="alert" className="alert alert-warning alert-soft shadow-sm">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="w-5 h-5 shrink-0"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </svg>
      <div className="flex-1 min-w-0">
        <h3 className="text-sm font-semibold">Daily limit reached</h3>
        <p className="text-xs opacity-80">
          You&apos;ve used {used} of {limit} daily {unit}. More {unit} free up{" "}
          {resetTime ? `at ${resetTime}` : "later today"}.
        </p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className="badge badge-warning badge-outline">
          {used}/{limit}
        </span>
        {onDismiss && (
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-circle"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
