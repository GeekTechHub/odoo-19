# -*- coding: utf-8 -*-
"""
Cliente HTTP para la API REST de la DGII (TesteCF y Producción).
Documentación de referencia:
  - TesteCF: https://ecf.dgii.gov.do/testecf/documentos/
  - Producción: https://ecf.dgii.gov.do/ecf/documentos/
"""
import logging
import requests

_logger = logging.getLogger(__name__)

# URLs base por entorno
API_URLS = {
    'test': 'https://ecf.dgii.gov.do/TesteCF',
    'prod': 'https://ecf.dgii.gov.do/eCF',
}

# Endpoints
ENDPOINTS = {
    'recepcion':         '/api/Recepcion',
    'consulta_estado':   '/api/ConsultaEstadoNCF',
    'consulta_track':    '/api/ConsultaTrackId',
    'token':             '/api/Autenticacion/api_key',
}

REQUEST_TIMEOUT = 30  # segundos


class DGIIClient:
    """
    Cliente para la API de facturación electrónica de la DGII.

    Referencia técnica: Manual del API e-CF DGII v2.1
    """

    def __init__(self, company):
        self.company = company
        env = company.ecf_api_env or 'test'
        self.base_url = API_URLS[env]
        self.token = company.ecf_api_token or ''

    # ── Envío del e-CF ────────────────────────────────────────────────────────

    def send_ecf(self, signed_xml: str, move) -> dict:
        """
        Envía el XML firmado a la DGII.

        :param signed_xml:  XML firmado como string
        :param move:        account.move (para datos adicionales)
        :return:            dict con la respuesta de la DGII
        """
        url = self.base_url + ENDPOINTS['recepcion']
        headers = self._build_headers(content_type='application/xml')

        _logger.info(
            'Enviando e-CF %s a DGII [%s]',
            move.ref or move.name,
            self.company.ecf_api_env,
        )

        try:
            response = requests.post(
                url,
                data=signed_xml.encode('utf-8'),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=True,
            )
            response.raise_for_status()
            return self._parse_response(response)

        except requests.exceptions.Timeout:
            _logger.error('Timeout enviando e-CF a DGII')
            raise Exception('Timeout de conexión con la DGII. Intente nuevamente.')
        except requests.exceptions.SSLError as e:
            _logger.error('Error SSL con DGII: %s', e)
            raise Exception('Error de certificado SSL con la DGII: %s' % str(e))
        except requests.exceptions.ConnectionError as e:
            _logger.error('Error de conexión con DGII: %s', e)
            raise Exception('No se pudo conectar con la DGII. Verifique su conexión.')
        except requests.exceptions.HTTPError as e:
            _logger.error('HTTP Error DGII: %s – %s', e.response.status_code, e.response.text)
            return self._parse_error_response(e.response)

    # ── Consulta de estado por Track ID ───────────────────────────────────────

    def check_status(self, track_id: str, move) -> dict:
        """
        Consulta el estado de un e-CF usando su track_id.

        :param track_id:  Track ID devuelto por la DGII al enviar
        :param move:      account.move (para contexto)
        :return:          dict con estado actual
        """
        url = self.base_url + ENDPOINTS['consulta_track']
        headers = self._build_headers()

        params = {
            'trackId': track_id,
            'rnc': (self.company.vat or '').replace('-', ''),
        }

        _logger.info('Consultando estado e-CF track_id=%s', track_id)

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=True,
            )
            response.raise_for_status()
            return self._parse_response(response)

        except requests.exceptions.HTTPError as e:
            return self._parse_error_response(e.response)
        except Exception as e:
            _logger.error('Error consultando estado DGII: %s', e)
            raise Exception('Error consultando estado: %s' % str(e))

    # ── Consulta de estado por NCF ─────────────────────────────────────────────

    def check_status_by_ncf(self, ncf: str, rnc_comprador: str) -> dict:
        """
        Consulta el estado de un e-CF por número de comprobante.

        :param ncf:           Número de e-CF (ej: E310000000001)
        :param rnc_comprador: RNC del comprador
        :return:              dict con estado
        """
        url = self.base_url + ENDPOINTS['consulta_estado']
        headers = self._build_headers()

        params = {
            'RNCEmisor': (self.company.vat or '').replace('-', ''),
            'NCF': ncf,
            'RNCComprador': (rnc_comprador or '').replace('-', ''),
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                verify=True,
            )
            response.raise_for_status()
            return self._parse_response(response)
        except requests.exceptions.HTTPError as e:
            return self._parse_error_response(e.response)

    # ── Obtención de token (si aplica) ────────────────────────────────────────

    def get_token(self, api_key: str) -> str:
        """
        Obtiene un token de acceso usando el API key de la empresa.
        Algunos entornos requieren autenticación previa.

        :param api_key: API Key provista por la DGII
        :return:        Token de acceso
        """
        url = self.base_url + ENDPOINTS['token']

        try:
            response = requests.post(
                url,
                json={'api_key': api_key},
                headers={'Content-Type': 'application/json'},
                timeout=REQUEST_TIMEOUT,
                verify=True,
            )
            response.raise_for_status()
            data = response.json()
            return data.get('token', '')
        except Exception as e:
            _logger.error('Error obteniendo token DGII: %s', e)
            raise Exception('No se pudo obtener token de la DGII: %s' % str(e))

    # ── Utilidades ─────────────────────────────────────────────────────────────

    def _build_headers(self, content_type: str = 'application/json') -> dict:
        headers = {
            'Content-Type': content_type,
            'Accept': 'application/json',
        }
        if self.token:
            headers['Authorization'] = 'Bearer %s' % self.token
        return headers

    @staticmethod
    def _parse_response(response: requests.Response) -> dict:
        """Parsea la respuesta JSON de la DGII."""
        content_type = response.headers.get('Content-Type', '')

        if 'application/json' in content_type:
            try:
                return response.json()
            except ValueError:
                pass

        # Fallback: intentar parsear como JSON de todas formas
        try:
            return response.json()
        except ValueError:
            # Si no es JSON, devolver respuesta genérica
            return {
                'estado': '0',
                'mensaje': response.text[:500],
                'trackId': None,
                'codigo': str(response.status_code),
            }

    @staticmethod
    def _parse_error_response(response: requests.Response) -> dict:
        """Parsea una respuesta de error HTTP."""
        try:
            data = response.json()
            return {
                'estado': '3',  # Rechazado
                'mensaje': data.get('mensaje', data.get('message', response.text[:200])),
                'trackId': None,
                'codigo': str(response.status_code),
            }
        except ValueError:
            return {
                'estado': '3',
                'mensaje': 'Error HTTP %s: %s' % (response.status_code, response.text[:200]),
                'trackId': None,
                'codigo': str(response.status_code),
            }
