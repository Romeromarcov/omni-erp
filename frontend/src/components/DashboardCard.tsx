import React from 'react';
import './DashboardCard.css';

interface DashboardCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: 'up' | 'down';
}

export const DashboardCard: React.FC<DashboardCardProps> = ({ title, value, subtitle, trend }) => (
  <div className={`dashboard-card ${trend ? `trend-${trend}` : ''}`}>
    <div className="dashboard-card-title">{title}</div>
    <div className="dashboard-card-value">{value}</div>
    {subtitle && <div className="dashboard-card-subtitle">{subtitle}</div>}
  </div>
);
