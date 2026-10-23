import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, BarChart3, Clock, LineChart, Wind } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client.js';

export const Navbar: React.FC = () => {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: apiClient.getHealth,
    refetchInterval: 30000,
  });

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <NavLink to="/" className="brand" aria-label="BMRS Wind Forecast Monitor Home">
          <div className="brand-icon">
            <Wind size={22} />
          </div>
          <div>
            <div className="brand-title">BMRS Wind Monitor</div>
            <div className="brand-subtitle">UK Day-Ahead Forecast Monitoring</div>
          </div>
        </NavLink>

        <nav className="nav-links" aria-label="Main Navigation">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          >
            <LineChart size={16} />
            <span>Forecast & Outturn</span>
          </NavLink>
          <NavLink
            to="/accuracy"
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          >
            <BarChart3 size={16} />
            <span>Accuracy & Horizons</span>
          </NavLink>
        </nav>

        <div className="nav-status">
          <div className="badge" title="Market Timezone Europe/London">
            <Clock size={12} />
            <span>Europe/London</span>
          </div>
          <div
            className="badge"
            title={health?.data_loaded ? 'Parquet snapshots active' : 'Connecting to API...'}
          >
            <span
              className="badge-dot"
              style={{
                backgroundColor: health?.data_loaded ? 'var(--emerald-actual)' : 'var(--amber-over)',
                boxShadow: `0 0 8px ${health?.data_loaded ? 'var(--emerald-actual)' : 'var(--amber-over)'}`,
              }}
            />
            <Activity size={12} />
            <span>{health?.data_loaded ? 'Snapshot data: Jan 2026' : 'Offline'}</span>
          </div>
        </div>
      </div>
    </header>
  );
};
