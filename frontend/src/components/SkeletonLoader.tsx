import React from 'react';

interface SkeletonLoaderProps {
  cardsCount?: number;
  showChart?: boolean;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({
  cardsCount = 4,
  showChart = true,
}) => {
  return (
    <div className="skeleton-container" aria-busy="true" aria-label="Loading data">
      <div className="kpi-grid">
        {Array.from({ length: cardsCount }).map((_, i) => (
          <div key={i} className="skeleton-card">
            <div className="skeleton-line skeleton-title" />
            <div className="skeleton-line skeleton-value" />
            <div className="skeleton-line skeleton-subtitle" />
          </div>
        ))}
      </div>
      {showChart && (
        <div className="skeleton-chart-card">
          <div className="skeleton-line skeleton-chart-header" />
          <div className="skeleton-chart-box" />
        </div>
      )}
    </div>
  );
};
