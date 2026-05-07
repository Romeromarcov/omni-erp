import React from 'react';

interface RoleListProps {
  roles: { id: number; name: string }[];
}

const RoleList: React.FC<RoleListProps> = ({ roles }) => (
  <ul style={{ listStyle: 'none', padding: 0 }}>
    {roles.map(role => (
      <li key={role.id} style={{ padding: '4px 0' }}>
        <span style={{ background: '#eee', borderRadius: 4, padding: '2px 8px' }}>{role.name}</span>
      </li>
    ))}
  </ul>
);

export default RoleList;
