# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    # ── Certificado digital ──────────────────────────────────────────────────
    ecf_certificate = fields.Binary(
        string='Certificado Digital (.p12)',
        help='Certificado digital en formato PKCS#12 (.p12) emitido por INDOTEL/DGII',
    )
    ecf_certificate_filename = fields.Char(string='Nombre del Certificado')
    ecf_certificate_password = fields.Char(
        string='Contraseña del Certificado',
        groups='base.group_system',
    )

    # ── Credenciales API DGII ────────────────────────────────────────────────
    ecf_api_env = fields.Selection(
        selection=[
            ('test', 'Pruebas (TesteCF)'),
            ('prod', 'Producción'),
        ],
        string='Entorno API DGII',
        default='test',
        required=True,
    )
    ecf_api_token = fields.Char(
        string='Token API DGII',
        groups='base.group_system',
        help='Token de autenticación para la API de la DGII',
    )

    # ── RNC / identificación ─────────────────────────────────────────────────
    ecf_rnc = fields.Char(
        string='RNC Emisor',
        related='vat',
        store=True,
    )
    ecf_trade_name = fields.Char(string='Nombre Comercial')
    ecf_business_activity = fields.Char(
        string='Actividad Económica',
        help='Código de actividad económica según DGII',
    )
