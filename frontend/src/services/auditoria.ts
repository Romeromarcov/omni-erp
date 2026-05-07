import { get } from './api';
import type { AuditLog } from '../pages/Core/Auditoria/AuditLogListPage';

export async function fetchAuditLogs(): Promise<AuditLog[] | { results: AuditLog[] }> {
  return get('/auditoria/logs-auditoria/');
}
