# -*- coding: utf-8 -*-
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EcfCertificate(models.Model):
    """
    Modelo para gestionar certificados digitales (.p12) utilizados
    en la firma de comprobantes fiscales electrónicos (e-CF).
    """
    _name = 'ecf.certificate'
    _description = 'Certificado Digital e-CF'
    _order = 'date_end desc'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    certificate_file = fields.Binary(
        string='Archivo Certificado (.p12)',
        required=True,
        attachment=False,
    )
    certificate_filename = fields.Char(
        string='Nombre de Archivo',
    )
    password = fields.Char(
        string='Contraseña del Certificado',
        required=True,
    )
    date_start = fields.Date(
        string='Fecha de Inicio',
        compute='_compute_dates',
        store=True,
    )
    date_end = fields.Date(
        string='Fecha de Vencimiento',
        compute='_compute_dates',
        store=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('valid', 'Válido'),
        ('expired', 'Expirado'),
    ], string='Estado', default='draft', compute='_compute_state', store=True)
    serial_number = fields.Char(
        string='Número de Serie',
        compute='_compute_dates',
        store=True,
    )
    subject = fields.Char(
        string='Sujeto',
        compute='_compute_dates',
        store=True,
    )
    active = fields.Boolean(default=True)

    @api.depends('certificate_file', 'password')
    def _compute_dates(self):
        for record in self:
            if not record.certificate_file or not record.password:
                record.date_start = False
                record.date_end = False
                record.serial_number = False
                record.subject = False
                continue
            try:
                from cryptography.hazmat.primitives.serialization import pkcs12
                cert_data = base64.b64decode(record.certificate_file)
                password_bytes = record.password.encode('utf-8')
                _, cert, _ = pkcs12.load_key_and_certificates(
                    cert_data, password_bytes
                )
                if cert:
                    record.date_start = cert.not_valid_before_utc.date()
                    record.date_end = cert.not_valid_after_utc.date()
                    record.serial_number = str(cert.serial_number)
                    record.subject = cert.subject.rfc4514_string()
                else:
                    record.date_start = False
                    record.date_end = False
                    record.serial_number = False
                    record.subject = False
            except Exception as e:
                _logger.warning("Error leyendo certificado: %s", str(e))
                record.date_start = False
                record.date_end = False
                record.serial_number = False
                record.subject = False

    @api.depends('date_end')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            if not record.date_end:
                record.state = 'draft'
            elif record.date_end < today:
                record.state = 'expired'
            else:
                record.state = 'valid'

    def action_validate(self):
        """Validar que el certificado puede ser leído correctamente."""
        self.ensure_one()
        try:
            from cryptography.hazmat.primitives.serialization import pkcs12
            cert_data = base64.b64decode(self.certificate_file)
            password_bytes = self.password.encode('utf-8')
            private_key, cert, _ = pkcs12.load_key_and_certificates(
                cert_data, password_bytes
            )
            if not private_key or not cert:
                raise UserError(_("El certificado no contiene clave privada o certificado público."))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Certificado Válido'),
                    'message': _('El certificado digital fue validado correctamente.'),
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(_("Error validando certificado: %s") % str(e))
