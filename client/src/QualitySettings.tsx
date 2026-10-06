type Quality = {
  concurrent_downloads?: number;
  fallback_profile?: string;
  fallback_minutes?: number;
  recheck_hours?: number;
};
export function QualitySettings({
  value,
  onChange,
}: {
  value: Quality;
  onChange: (value: Quality) => void;
}) {
  return (
    <div className="quality-settings">
      <h3>Quality policy &amp; transfer limits</h3>
      <p>
        Album preferences override artist preferences, which override the system
        quality above. Changing the system quality re-downloads managed music
        that follows it. A successful replacement removes the old download.
      </p>
      <label className="download-option">
        When lossless is unavailable
        <select
          aria-label="Lossless fallback quality"
          value={value.fallback_profile || "mp3_320"}
          onChange={(e) =>
            onChange({ ...value, fallback_profile: e.target.value })
          }
        >
          <option value="mp3_320">Allow MP3 320 kbps</option>
          <option value="mp3_128">Allow MP3 128 kbps or better</option>
          <option value="none">Wait for lossless</option>
        </select>
      </label>
      {[
        [
          "fallback_minutes",
          "Preferred-quality time limit (minutes)",
          10,
          1,
          60,
        ],
        ["recheck_hours", "Check for upgrades every (hours)", 24, 1, 168],
        ["concurrent_downloads", "Simultaneous downloads", 3, 1, 6],
      ].map(([key, label, initial, min, max]) => (
        <label className="download-option" key={String(key)}>
          {label}
          <input
            type="number"
            aria-label={String(label)}
            min={Number(min)}
            max={Number(max)}
            value={value[key as keyof Quality] ?? initial}
            onChange={(e) =>
              onChange({ ...value, [key]: Number(e.target.value) })
            }
          />
        </label>
      ))}
      <p>
        Fallback begins when preferred sources are exhausted or their time limit
        is reached. Upgrade checks never replace a saved song with a
        lower-quality file. Each Soulseek peer handles one transfer at a time.
      </p>
    </div>
  );
}
