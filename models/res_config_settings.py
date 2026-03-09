# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ecf_certificate = fields.Binary(
        related='company_id.ecf_certificate',
        readonly=False,
        string='Certificado Digital (.p12)',
    )
    ecf_certificate_filename = fields.Char(
        related='company_id.ecf_certificate_filename',
        readonly=False,
    )
    ecf_certificate_password = fields.Char(
        related='company_id.ecf_certificate_password',
        readonly=False,
        string='Contraseña Certificado',
    )
    ecf_api_env = fields.Selection(
        related='company_id.ecf_api_env',
        readonly=False,
        string='Entorno DGII',
    )
    ecf_api_token = fields.Char(
        related='company_id.ecf_api_token',
        readonly=False,
        string='Token API DGII',
    )
    ecf_trade_name = fields.Char(
        related='company_id.ecf_trade_name',
        readonly=False,
        string='Nombre Comercial',
    )
    ecf_business_activity = fields.Char(
        related='company_id.ecf_business_activity',
        readonly=False,
        string='Actividad Económica',
    )
