import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({
  title = 'Failed to load data',
  message,
  onRetry,
}) => {
  return (
    <div className="state-container" role="alert">
      <div style={{ color: 'var(--rose-under)' }}>
        <AlertTriangle size={36} />
      </div>
      <div>
        <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--text-main)' }}>
          {title}
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
          {message}
        </p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-primary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}
        >
          <RefreshCw size={14} />
          <span>Retry</span>
        </button>
      )}
    </div>
  );
};
