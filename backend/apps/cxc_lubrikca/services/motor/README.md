# Motor determinístico (`services/motor/`)

Port puro del motor de cálculo de CxC desde `CxC_Lubrikca/src/cxc` — **Django-free**.
Opera sobre sus propias dataclasses (contrato interno del motor), no sobre modelos
Django ni Odoo. El bridge desde la config Django/Odoo hacia estas dataclasses es
**Fase 3**. Las pruebas de paridad viven en `backend/tests/cxc_lubrikca/motor/`.
