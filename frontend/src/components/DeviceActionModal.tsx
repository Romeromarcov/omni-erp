import React, { useState } from 'react';
import { DispositivoService } from '../services/dispositivoService';
import type { DispositivoInfo } from '../types/dispositivos';

interface DeviceActionModalProps {
  dispositivoInfo: DispositivoInfo;
  onActionComplete: (success: boolean, dispositivoInfo?: DispositivoInfo) => void;
  onClose: () => void;
}

export const DeviceActionModal: React.FC<DeviceActionModalProps> = ({
  dispositivoInfo,
  onActionComplete,
  onClose
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [nombreCaja, setNombreCaja] = useState('');
  const [tipoCaja, setTipoCaja] = useState('REGISTRADORA');
  const [error, setError] = useState('');

  const handleCrearCaja = async () => {
    if (!nombreCaja.trim()) {
      setError('El nombre de la caja es requerido');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const response = await DispositivoService.crearCajaFisica(
        dispositivoInfo.id_dispositivo,
        nombreCaja.trim(),
        tipoCaja
      );

      if (response.success) {
        onActionComplete(true, {
          ...dispositivoInfo,
          accion: 'abrir_sesion',
          mensaje: response.mensaje,
          sesion_abierta: response.sesion
        });
      } else {
        setError(response.error || 'Error al crear la caja física');
      }
    } catch (err) {
      console.error('Error creando caja física:', err);
      setError('Error al crear la caja física. Intente nuevamente.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNoPreguntar = async () => {
    setIsLoading(true);
    setError('');

    try {
      const response = await DispositivoService.noPreguntarCaja(dispositivoInfo.id_dispositivo);

      if (response.success) {
        onActionComplete(true, {
          ...dispositivoInfo,
          accion: 'nada',
          mensaje: response.mensaje
        });
      } else {
        setError(response.error || 'Error al actualizar dispositivo');
      }
    } catch (err) {
      console.error('Error actualizando dispositivo:', err);
      setError('Error al actualizar dispositivo. Intente nuevamente.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAbrirSesion = async () => {
    setIsLoading(true);
    setError('');

    try {
      const response = await DispositivoService.abrirSesion(dispositivoInfo.id_dispositivo);

      if (response.success) {
        onActionComplete(true, {
          ...dispositivoInfo,
          accion: 'abrir_sesion',
          mensaje: response.mensaje,
          sesion_abierta: response.sesion
        });
      } else {
        setError(response.error || 'Error al abrir sesión');
      }
    } catch (err) {
      console.error('Error abriendo sesión:', err);
      setError('Error al abrir sesión. Intente nuevamente.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Detección de Dispositivo
          </h2>
          <p className="text-gray-600 text-sm mb-4">
            {dispositivoInfo.mensaje}
          </p>
        </div>

        {dispositivoInfo.accion === 'preguntar_caja' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="nombreCaja" className="block text-sm font-medium text-gray-700 mb-1">
                Nombre de la Caja Física
              </label>
              <input
                id="nombreCaja"
                type="text"
                value={nombreCaja}
                onChange={(e) => setNombreCaja(e.target.value)}
                placeholder={`Caja ${dispositivoInfo.nombre_dispositivo}`}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={isLoading}
              />
            </div>

            <div>
              <label htmlFor="tipoCaja" className="block text-sm font-medium text-gray-700 mb-1">
                Tipo de Caja
              </label>
              <select
                id="tipoCaja"
                value={tipoCaja}
                onChange={(e) => setTipoCaja(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={isLoading}
              >
                <option value="REGISTRADORA">Caja Registradora</option>
                <option value="GERENCIA">Caja Gerente Sucursal</option>
                <option value="MATRIZ">Caja Matriz/Principal</option>
                <option value="OTRO">Otro</option>
              </select>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        )}

        <div className="mt-6 flex space-x-3">
          {dispositivoInfo.accion === 'preguntar_caja' && (
            <>
              <button
                onClick={handleCrearCaja}
                disabled={isLoading || !nombreCaja.trim()}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Creando...' : 'Crear Caja y Abrir Sesión'}
              </button>
              <button
                onClick={handleNoPreguntar}
                disabled={isLoading}
                className="flex-1 px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Procesando...' : 'No Preguntar Más'}
              </button>
            </>
          )}

          {dispositivoInfo.accion === 'abrir_sesion' && (
            <button
              onClick={handleAbrirSesion}
              disabled={isLoading}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? 'Abriendo Sesión...' : 'Abrir Sesión'}
            </button>
          )}

          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 bg-gray-200 text-gray-800 rounded-md hover:bg-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancelar
          </button>
        </div>

        <div className="mt-4 text-xs text-gray-500">
          <p>Dispositivo: {dispositivoInfo.nombre_dispositivo}</p>
          {dispositivoInfo.creado && (
            <p className="text-green-600">✓ Dispositivo registrado por primera vez</p>
          )}
        </div>
      </div>
    </div>
  );
};