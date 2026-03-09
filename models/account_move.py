# -*- coding: utf-8 -*-
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ── Constantes de tipos e-CF ─────────────────────────────────────────────────
ECF_TYPES = [
    ('e31', 'e31 - Factura de Crédito Fiscal Electrónica'),
    ('e32', 'e32 - Factura de Consumo Electrónica'),
    ('e33', 'e33 - Nota de Débito Electrónica'),
    ('e34', 'e34 - Nota de Crédito Electrónica'),
    ('e41', 'e41 - Compras Electrónico'),
    ('e43', 'e43 - Gastos Menores Electrónico'),
    ('e44', 'e44 - Regímenes Especiales Electrónico'),
    ('e45', 'e45 - Gubernamental Electrónico'),
    ('e46', 'e46 - Exportación Electrónica'),
    ('e47', 'e47 - Pagos al Exterior Electrónico'),
]

ECF_STATES = [
    ('not_sent', 'No Enviado'),
    ('sent', 'Enviado'),
    ('accepted', 'Aceptado'),
    ('accepted_with_obs', 'Aceptado con Observaciones'),
    ('rejected', 'Rechazado'),
    ('error', 'Error'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ── Campos e-CF ──────────────────────────────────────────────────────────
    ecf_enabled = fields.Boolean(
        string='Factura Electrónica (e-CF)',
        compute='_compute_ecf_enabled',
        store=True,
    )
    ecf_type = fields.Selection(
        selection=ECF_TYPES,
        string='Tipo e-CF',
        compute='_compute_ecf_type',
        store=True,
        readonly=False,
    )
    ecf_state = fields.Selection(
        selection=ECF_STATES,
        string='Estado e-CF',
        default='not_sent',
        tracking=True,
        copy=False,
    )
    ecf_track_id = fields.Char(
        string='Track ID (DGII)',
        copy=False,
        readonly=True,
        help='Identificador de seguimiento devuelto por la DGII',
    )
    ecf_xml = fields.Text(
        string='XML e-CF',
        copy=False,
        readonly=True,
    )
    ecf_xml_signed = fields.Text(
        string='XML Firmado',
        copy=False,
        readonly=True,
    )
    ecf_qr_code = fields.Binary(
        string='Código QR e-CF',
        copy=False,
        readonly=True,
    )
    ecf_response_code = fields.Char(
        string='Código Respuesta DGII',
        copy=False,
        readonly=True,
    )
    ecf_response_message = fields.Text(
        string='Mensaje Respuesta DGII',
        copy=False,
        readonly=True,
    )
    ecf_send_date = fields.Datetime(
        string='Fecha de Envío',
        copy=False,
        readonly=True,
    )
    ecf_acceptance_date = fields.Datetime(
        string='Fecha de Aceptación',
        copy=False,
        readonly=True,
    )
    ecf_security_code = fields.Char(
        string='Código de Seguridad',
        copy=False,
        readonly=True,
        help='Código de seguridad incluido en el QR del e-CF',
    )

    # ── Cómputos ─────────────────────────────────────────────────────────────
    @api.depends('move_type', 'journal_id', 'company_id.country_id')
    def _compute_ecf_enabled(self):
        """Activa e-CF para compañías dominicanas con diarios de facturación."""
        for move in self:
            is_do = move.company_id.country_id.code == 'DO'
            is_invoice = move.move_type in (
                'out_invoice', 'out_refund',
                'in_invoice', 'in_refund',
            )
            move.ecf_enabled = is_do and is_invoice

    @api.depends('move_type', 'partner_id', 'partner_id.vat', 'journal_id')
    def _compute_ecf_type(self):
        """Determina el tipo de e-CF basado en el tipo de factura y el partner."""
        for move in self:
            if not move.ecf_enabled:
                move.ecf_type = False
                continue

            if move.move_type == 'out_invoice':
                partner_vat = (move.partner_id.vat or '').strip()
                # Si el partner tiene RNC (9 dígitos) → Crédito Fiscal
                if partner_vat and len(partner_vat) == 9:
                    move.ecf_type = 'e31'
                else:
                    move.ecf_type = 'e32'
            elif move.move_type == 'out_refund':
                move.ecf_type = 'e34'
            elif move.move_type == 'in_invoice':
                move.ecf_type = 'e41'
            elif move.move_type == 'in_refund':
                move.ecf_type = 'e33'
            else:
                move.ecf_type = False

    # ── Estado legible ────────────────────────────────────────────────────────
    @property
    def ecf_state_label(self):
        labels = dict(ECF_STATES)
        return labels.get(self.ecf_state, self.ecf_state)

    # ── Acciones principales ──────────────────────────────────────────────────
    def action_send_ecf(self):
        """Genera, firma y envía el e-CF a la DGII."""
        self.ensure_one()
        if not self.ecf_enabled:
            raise UserError(_('Esta factura no requiere e-CF.'))
        if self.state != 'posted':
            raise UserError(_('Solo se pueden enviar facturas confirmadas.'))
        if self.ecf_state in ('accepted', 'accepted_with_obs'):
            raise UserError(_('Este e-CF ya fue aceptado por la DGII.'))

        company = self.company_id
        if not company.ecf_certificate:
            raise UserError(_(
                'Configure el certificado digital en Ajustes → '
                'Facturación Electrónica.'
            ))

        try:
            # 1. Generar XML
            xml_generator = self._get_xml_generator()
            xml_content = xml_generator.generate(self)
            self.ecf_xml = xml_content
            _logger.info('e-CF XML generado para %s', self.name)

            # 2. Firmar XML
            xml_signer = self._get_xml_signer()
            cert_data = base64.b64decode(company.ecf_certificate)
            signed_xml = xml_signer.sign(
                xml_content,
                cert_data,
                company.ecf_certificate_password or '',
            )
            self.ecf_xml_signed = signed_xml
            _logger.info('e-CF XML firmado para %s', self.name)

            # 3. Enviar a la DGII
            dgii_client = self._get_dgii_client()
            response = dgii_client.send_ecf(signed_xml, self)

            self._process_dgii_response(response)

            # 4. Generar QR
            self._generate_qr_code()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('e-CF Enviado'),
                    'message': _(
                        'El comprobante fue enviado a la DGII. '
                        'Track ID: %s'
                    ) % (self.ecf_track_id or '-'),
                    'type': 'success',
                    'sticky': False,
                },
            }

        except UserError:
            raise
        except Exception as exc:
            _logger.exception('Error enviando e-CF %s', self.name)
            self.ecf_state = 'error'
            self.ecf_response_message = str(exc)
            raise UserError(
                _('Error al enviar el e-CF: %s') % str(exc)
            )

    def action_check_ecf_status(self):
        """Consulta el estado del e-CF en la DGII usando el track_id."""
        self.ensure_one()
        if not self.ecf_track_id:
            raise UserError(_(
                'No hay Track ID para consultar. Envíe el e-CF primero.'
            ))

        try:
            dgii_client = self._get_dgii_client()
            response = dgii_client.check_status(self.ecf_track_id, self)
            self._process_dgii_status_response(response)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Estado e-CF'),
                    'message': _('Estado actualizado: %s') % self.ecf_state_label,
                    'type': 'info',
                    'sticky': False,
                },
            }
        except Exception as exc:
            _logger.exception('Error consultando estado e-CF %s', self.name)
            raise UserError(
                _('Error consultando estado: %s') % str(exc)
            )

    def action_view_ecf_xml(self):
        """Abre un wizard para visualizar el XML del e-CF."""
        self.ensure_one()
        xml_to_show = self.ecf_xml_signed or self.ecf_xml
        if not xml_to_show:
            raise UserError(_('Aún no se ha generado el XML del e-CF.'))

        return {
            'type': 'ir.actions.act_window',
            'name': _('XML e-CF - %s') % self.name,
            'res_model': 'dgii.ecf.xml.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_xml_content': xml_to_show,
            },
        }

    # ── Helpers: instanciación de servicios ──────────────────────────────────
    def _get_xml_generator(self):
        from ..services.xml_generator import ECFXmlGenerator
        return ECFXmlGenerator()

    def _get_xml_signer(self):
        from ..services.xml_signer import ECFXmlSigner
        return ECFXmlSigner()

    def _get_dgii_client(self):
        from ..services.dgii_client import DGIIClient
        return DGIIClient(self.company_id)

    # ── Procesamiento de respuestas DGII ─────────────────────────────────────
    def _process_dgii_response(self, response):
        """Interpreta la respuesta de envío de la DGII."""
        fields.Datetime_ = fields.Datetime
        self.ecf_send_date = fields.Datetime.now()
        self.ecf_track_id = response.get('trackId') or response.get('track_id')
        self.ecf_response_code = str(response.get('codigo', ''))
        self.ecf_response_message = response.get('mensaje', '')

        status_map = {
            '1': 'accepted',
            '2': 'accepted_with_obs',
            '3': 'rejected',
        }
        api_status = str(response.get('estado', ''))
        self.ecf_state = status_map.get(api_status, 'sent')

        if self.ecf_state in ('accepted', 'accepted_with_obs'):
            self.ecf_acceptance_date = fields.Datetime.now()

    def _process_dgii_status_response(self, response):
        """Interpreta la respuesta de consulta de estado de la DGII."""
        status_map = {
            'Aceptado': 'accepted',
            'AceptadoCondicional': 'accepted_with_obs',
            'Rechazado': 'rejected',
            'EnProceso': 'sent',
        }
        raw_status = response.get('estado', response.get('status', ''))
        new_state = status_map.get(raw_status, self.ecf_state)

        self.ecf_state = new_state
        self.ecf_response_message = response.get('mensaje', self.ecf_response_message)

        if new_state in ('accepted', 'accepted_with_obs') and not self.ecf_acceptance_date:
            self.ecf_acceptance_date = fields.Datetime.now()

    # ── Generación de QR ─────────────────────────────────────────────────────
    def _generate_qr_code(self):
        """Genera el código QR del e-CF con los datos requeridos por la DGII."""
        try:
            import qrcode
            import io

            qr_data = self._build_qr_data()
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=6,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)

            img = qr.make_image(fill_color='black', back_color='white')
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            self.ecf_qr_code = base64.b64encode(buffer.getvalue())
            _logger.info('QR generado para e-CF %s', self.name)

        except ImportError:
            _logger.warning('qrcode no instalado. No se generó el QR.')
        except Exception as exc:
            _logger.warning('Error generando QR: %s', exc)

    def _build_qr_data(self):
        """Construye la cadena de datos del QR según el formato DGII."""
        company = self.company_id
        partner = self.partner_id
        # Formato oficial DGII para QR del e-CF
        parts = [
            ('RncEmisor', (company.vat or '').replace('-', '')),
            ('RncComprador', (partner.vat or '').replace('-', '')),
            ('ENCF', self.ref or ''),
            ('FechaEmision', self.invoice_date.strftime('%d-%m-%Y') if self.invoice_date else ''),
            ('MontoTotal', '%.2f' % (self.amount_total or 0.0)),
            ('ITBIS', '%.2f' % (self._get_tax_amount() or 0.0)),
            ('TrackID', self.ecf_track_id or ''),
        ]
        return '&'.join('%s=%s' % (k, v) for k, v in parts if v)

    def _get_tax_amount(self):
        """Obtiene el monto de ITBIS de la factura."""
        tax_lines = self.line_ids.filtered(
            lambda l: l.tax_line_id and 'ITBIS' in (l.tax_line_id.name or '').upper()
        )
        return sum(abs(l.balance) for l in tax_lines)

    # ── Override de _post para envío automático (opcional) ───────────────────
    def _post(self, soft=True):
        """Si la compañía usa envío automático, envía el e-CF al confirmar."""
        result = super()._post(soft=soft)
        # El envío automático puede activarse por configuración (no forzado)
        # Se deja como hook para customizaciones
        return result
