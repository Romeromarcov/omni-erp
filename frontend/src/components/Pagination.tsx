import React from 'react';

interface PaginationProps {
  page: number;
  count: number;
  pageSize?: number;
  onChange: (page: number) => void;
}

const Pagination: React.FC<PaginationProps> = ({ page, count, pageSize = 20, onChange }) => {
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  if (totalPages <= 1) return null;

  const pages: (number | '...')[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push('...');
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
    if (page < totalPages - 2) pages.push('...');
    pages.push(totalPages);
  }

  const btnStyle = (active: boolean, disabled?: boolean): React.CSSProperties => ({
    padding: '6px 12px',
    border: `1px solid ${active ? '#1976d2' : '#dee2e6'}`,
    borderRadius: 6,
    background: active ? '#1976d2' : disabled ? '#f8f9fa' : '#fff',
    color: active ? '#fff' : disabled ? '#adb5bd' : '#212529',
    cursor: disabled ? 'default' : 'pointer',
    fontSize: 13,
    fontWeight: active ? 600 : 400,
    minWidth: 36,
    textAlign: 'center' as const,
  });

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        justifyContent: 'center',
        padding: '16px 0 8px',
        flexWrap: 'wrap',
      }}
    >
      <button
        style={btnStyle(false, page === 1)}
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
      >
        ‹
      </button>

      {pages.map((p, idx) =>
        p === '...' ? (
          <span key={`ellipsis-${idx}`} style={{ padding: '6px 4px', color: '#6c757d', fontSize: 13 }}>
            …
          </span>
        ) : (
          <button key={p} style={btnStyle(p === page)} onClick={() => p !== page && onChange(p)}>
            {p}
          </button>
        )
      )}

      <button
        style={btnStyle(false, page === totalPages)}
        disabled={page === totalPages}
        onClick={() => onChange(page + 1)}
      >
        ›
      </button>

      <span style={{ marginLeft: 8, fontSize: 12, color: '#6c757d' }}>
        {count.toLocaleString()} registros · pág {page}/{totalPages}
      </span>
    </div>
  );
};

export default Pagination;
