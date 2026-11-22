import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/server';
import { apiUrl } from '../../test/handlers';
import { setAccessToken, clearAccessToken } from '../api';
import {
  confirmarMfa,
  desactivarMfa,
  getMfaEstado,
  iniciarMfa,
  regenerarCodigosMfa,
  verificarMfaLogin,
} from '../mfa';
import { loginAndFetchUser, MfaChallengeError, verifyMfaAndFetchUser } from '../auth';

describe('mfa service & auth flow (MSW)', () => {
  beforeEach(() => {
    clearAccessToken();
  });

  it('consulta estado e inicia y confirma 2FA con Authorization header', async () => {
    setAccessToken('ci-jwt-token');
    let authHeader = '';

    server.use(
      http.get(apiUrl('/auth/mfa/estado/'), ({ request }) => {
        authHeader = request.headers.get('Authorization') ?? '';
        return HttpResponse.json({
          habilitado: false,
          confirmado_en: null,
          codigos_respaldo_restantes: 0,
          requerido_por_politica: true,
        });
      }),
      http.post(apiUrl('/auth/mfa/iniciar/'), () =>
        HttpResponse.json({
          otpauth_uri: 'otpauth://totp/Omni%20ERP:demo?secret=JBSWY3DPEHPK3PXP',
          qr_svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>',
          secret_manual: 'JBSWY3DPEHPK3PXP',
        }),
      ),
      http.post(apiUrl('/auth/mfa/confirmar/'), () =>
        HttpResponse.json({
          habilitado: true,
          confirmado_en: '2026-11-22T12:00:00Z',
          codigos_respaldo: ['ABCD-EFGH'],
        }),
      ),
      http.post(apiUrl('/auth/mfa/regenerar-codigos/'), () =>
        HttpResponse.json({ codigos_respaldo: ['ZZZZ-YYYY'] }),
      ),
      http.post(apiUrl('/auth/mfa/desactivar/'), () =>
        HttpResponse.json({ habilitado: false }),
      ),
    );

    const estado = await getMfaEstado();
    expect(estado.requerido_por_politica).toBe(true);
    expect(authHeader).toBe('Bearer ci-jwt-token');

    const init = await iniciarMfa();
    expect(init.secret_manual).toBe('JBSWY3DPEHPK3PXP');

    const conf = await confirmarMfa('123456');
    expect(conf.habilitado).toBe(true);
    expect(conf.codigos_respaldo).toEqual(['ABCD-EFGH']);

    const regen = await regenerarCodigosMfa('654321');
    expect(regen.codigos_respaldo).toEqual(['ZZZZ-YYYY']);

    const off = await desactivarMfa('pass-demo', 'ZZZZ-YYYY');
    expect(off.habilitado).toBe(false);
  });

  it('loginAndFetchUser lanza MfaChallengeError y verifyMfaAndFetchUser completa sesión', async () => {
    server.use(
      http.post(apiUrl('/auth/login/'), () =>
        HttpResponse.json({
          mfa_requerido: true,
          mfa_token: 'signed-mfa-token',
          metodo: 'TOTP',
        }),
      ),
      http.post(apiUrl('/auth/mfa/verificar/'), () =>
        HttpResponse.json({
          access: 'jwt-after-mfa',
        }),
      ),
      http.get(apiUrl('/core/usuarios/me/'), () =>
        HttpResponse.json({
          id: 'u-mfa-1',
          username: 'admin',
          empresas: [],
          sucursales: [],
        }),
      ),
      http.get(apiUrl('/core/usuario_roles/'), () => HttpResponse.json([])),
    );

    await expect(loginAndFetchUser('admin', 'secret')).rejects.toBeInstanceOf(MfaChallengeError);

    const direct = await verificarMfaLogin('signed-mfa-token', '123456');
    expect(direct.access).toBe('jwt-after-mfa');

    const session = await verifyMfaAndFetchUser('signed-mfa-token', '123456');
    expect(session.token).toBe('jwt-after-mfa');
    expect(session.usuario.username).toBe('admin');
  });
});
