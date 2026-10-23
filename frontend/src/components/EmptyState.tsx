import React from 'react';
import { Database } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  message?: string;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No generation data found',
  message = 'No data is available for the selected delivery window or parameters.',
  actionText,
  onAction,
}) => {
  return (
    <div className="empty-state-card" role="region" aria-label="No data">
      <div className="empty-state-icon">
        <Database size={28} />
      </div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
      {actionText && onAction && (
        <button type="button" onClick={onAction} className="btn-secondary" style={{ marginTop: '0.5rem' }}>
          {actionText}
        </button>
      )}
    </div>
  );
};
