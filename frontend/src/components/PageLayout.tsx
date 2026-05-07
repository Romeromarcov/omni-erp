import React from 'react';

interface PageLayoutProps {
  children: React.ReactNode;
  maxWidth?: number;
  style?: React.CSSProperties;
}

const PageLayout: React.FC<PageLayoutProps> = ({ children, maxWidth = 900, style }) => (
  <div className="vertical-center" style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)' }}>
    <div
      className="centered-container"
      style={{
        background: '#fff',
        borderRadius: 16,
        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
        padding: 32,
        maxWidth,
        margin: '32px auto',
        ...style,
      }}
    >
      {children}
    </div>
  </div>
);

export default PageLayout;
