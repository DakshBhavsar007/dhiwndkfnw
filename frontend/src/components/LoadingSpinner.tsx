import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'Loading wind generation data...',
}) => {
  return (
    <div className="state-container" role="status" aria-live="polite">
      <div className="spinner" />
      <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{message}</div>
    </div>
  );
};
