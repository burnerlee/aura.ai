import { ArrowUpRight, Sparkle } from "@phosphor-icons/react";
import { CATEGORIES, type InterestProfile } from "@aura/shared";

interface InterestPanelProps {
  profile: InterestProfile;
  onEdit: () => void;
}

export function InterestPanel({ profile, onEdit }: InterestPanelProps) {
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <aside className="interest-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">YOUR PROFILE</span>
          <h2>Interest DNA</h2>
        </div>
        <button className="icon-button subtle-icon" aria-label="Edit interests" onClick={onEdit}>
          <ArrowUpRight size={18} weight="bold" />
        </button>
      </div>

      <div className="dna-visual">
        <svg className="dna-chart" viewBox="0 0 120 120" aria-label="Interest vector composition">
          <circle
            className="dna-track"
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            strokeWidth="11"
          />
          <g transform="rotate(-90 60 60)">
            {CATEGORIES.map((category) => {
              const value = profile.vector[category.id];
              const segment = (value / 100) * circumference;
              const currentOffset = offset;
              offset += segment;
              return (
                <circle
                  key={category.id}
                  cx="60"
                  cy="60"
                  r={radius}
                  fill="none"
                  stroke={category.color}
                  strokeWidth="11"
                  strokeLinecap="round"
                  strokeDasharray={`${Math.max(segment - 3, 0)} ${circumference}`}
                  strokeDashoffset={-currentOffset}
                  className="dna-segment"
                />
              );
            })}
          </g>
        </svg>
        <div className="dna-center">
          <span className="dna-center-icon"><Sparkle size={15} weight="fill" /></span>
          <strong>LIVE</strong>
          <span>VECTOR</span>
        </div>
      </div>

      <div className="interest-legend">
        {CATEGORIES.map((category) => (
          <div className="interest-row" key={category.id}>
            <span className="interest-name">
              <i className="interest-dot" style={{ backgroundColor: category.color }} />
              {category.shortLabel}
            </span>
            <span className="interest-value">{Math.round(profile.vector[category.id])}%</span>
          </div>
        ))}
      </div>

      <div className="interest-prompt">
        <span className="prompt-label"><Sparkle size={13} weight="fill" /> ACTIVE SIGNAL</span>
        <p>“{profile.prompt}”</p>
        <button className="text-action" onClick={onEdit}>
          Tune your feed <ArrowUpRight size={14} weight="bold" />
        </button>
      </div>

      <div className="vector-note">
        <span className="vector-pulse" />
        Every resonate or banish updates this profile.
      </div>
    </aside>
  );
}
