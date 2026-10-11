export type QualityOption = { value: string; label: string; rank?: number };

/** Mirrors server/quality.py options(): best first, one label per profile. */
export const defaultQualityOptions: QualityOption[] = [
  { value: "lossless", label: "Lossless (FLAC)", rank: 4 },
  { value: "mp3_320", label: "MP3 320 kbps", rank: 3 },
  { value: "mp3_128", label: "MP3 128 kbps", rank: 2 },
  { value: "aac_256", label: "AAC 256 kbps", rank: 1 },
  {
    value: "native_standard",
    label: "Native audio (standard or better)",
    rank: 0.5,
  },
];

export function qualityLabel(
  value: string | null | undefined,
  options: QualityOption[] = defaultQualityOptions,
) {
  return options.find((o) => o.value === value)?.label ?? value ?? "";
}

export function QualitySelect({
  value,
  onChange,
  inheritLabel,
  options = defaultQualityOptions,
  disabled,
  label,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  /** Text for the "" option; omit when there is nothing to inherit from. */
  inheritLabel?: string;
  options?: QualityOption[];
  disabled?: boolean;
  label?: string;
  ariaLabel?: string;
}) {
  const select = (
    <select
      aria-label={ariaLabel ?? (label ? undefined : "Quality")}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {inheritLabel !== undefined && <option value="">{inheritLabel}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return label ? (
    <label>
      {label}
      {select}
    </label>
  ) : (
    select
  );
}
