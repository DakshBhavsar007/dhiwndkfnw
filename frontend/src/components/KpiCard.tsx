import React from 'react';

interface KpiCardProps {
  title: string;
  value: string;
  unit?: string;
  subtitle?: string;
  statusDot?: 'cyan' | 'amber' | 'rose' | 'emerald' | 'none';
}

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  unit,
  subtitle,
  statusDot = 'none',
}) => {
  return (
    <div className="kpi-card">
      <div className="kpi-header">
        <span className="kpi-label">{title}</span>
        {statusDot !== 'none' && <span className={`kpi-dot ${statusDot}`} />}
      </div>
      <div className="kpi-value-row">
        <span className="kpi-num tabular-nums">{value}</span>
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {subtitle && (
        <div className="kpi-helper" title={subtitle}>
          {subtitle}
        </div>
      )}
    </div>
  );
};
