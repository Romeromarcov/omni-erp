import React, { useState } from 'react';
import { createUsuario } from '../../../services/users';
import PageLayout from '../../../components/PageLayout';
import { getEmpresaId } from '../../../utils/empresa';

const UserCreatePage: React.FC = () => {
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    is_active: true,
    es_superusuario_innova: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [emailError, setEmailError] = useState('');
  const id_empresa = getEmpresaId() || undefined;

  const validateEmail = (email: string) => {
    // Simple regex for email validation
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
    if (name === 'email') {
      if (!validateEmail(value)) {
        setEmailError('Ingrese un email válido');
      } else {
        setEmailError('');
      }
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== confirmPassword) {
      setMessage('Las contraseñas no coinciden');
      return;
    }
    if (!validateEmail(form.email)) {
      setEmailError('Ingrese un email válido');
      setMessage('');
      return;
    }
    setLoading(true);
    try {
      await createUsuario({ ...form, id_empresa });
      setMessage('Usuario creado exitosamente');
      setForm({ username: '', email: '', password: '', first_name: '', last_name: '', is_active: true, es_superusuario_innova: false });
      setConfirmPassword('');
      setEmailError('');
    } catch {
      setMessage('Error al crear usuario');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Crear Nuevo Usuario</h2>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Username
          <input name="username" value={form.username} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email
          <input name="email" value={form.email} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15, borderColor: emailError ? '#d32f2f' : '#cfd8dc' }} />
          {emailError && <span style={{ color: '#d32f2f', fontSize: 13 }}>{emailError}</span>}
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Password
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              onChange={handleChange}
              required
              style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(v => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontWeight: 500 }}
              tabIndex={-1}
            >
              {showPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Confirmar contraseña
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              name="confirmPassword"
              type={showConfirmPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
              style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15,
                borderColor: confirmPassword && form.password !== confirmPassword ? '#d32f2f' : '#cfd8dc' }}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(v => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontWeight: 500 }}
              tabIndex={-1}
            >
              {showConfirmPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
          {confirmPassword && form.password !== confirmPassword && (
            <span style={{ color: '#d32f2f', fontSize: 13 }}>Las contraseñas no coinciden</span>
          )}
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre
          <input name="first_name" value={form.first_name} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Apellido
          <input name="last_name" value={form.last_name} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input name="is_active" type="checkbox" checked={form.is_active} onChange={handleChange} style={{ marginTop: 0 }} /> Activo
        </label>
        {/* Superusuario checkbox removed as requested */}
        <button type="submit" disabled={loading} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Crear usuario</button>
      </form>
      {message && <p style={{ marginTop: 18, textAlign: 'center', color: message.includes('exitosamente') ? '#388e3c' : '#d32f2f', fontWeight: 500 }}>{message}</p>}
    </PageLayout>
  );
};

export default UserCreatePage;
