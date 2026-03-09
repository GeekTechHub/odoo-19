# -*- coding: utf-8 -*-
{
    'name': 'Dominican Republic - Electronic Invoicing (e-CF)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/EDI',
    'summary': 'Facturación Electrónica DGII - Comprobante Fiscal Electrónico (e-CF)',
    'description': """
        Módulo de Facturación Electrónica para República Dominicana.
        Implementa el estándar e-CF de la DGII.

        Funcionalidades:
        ================
        * Generación de XML e-CF según especificaciones DGII (v1.0)
        * Firma digital de XML con certificado PKCS#12 (.p12) via RSA-SHA256
        * Envío automático a la DGII via API REST (TesteCF / Producción)
        * Seguimiento con Track ID devuelto por la DGII
        * Consulta de estado en tiempo real
        * Generación de código QR con datos del comprobante
        * Gestión de certificados digitales con control de vencimiento
        * Soporte para tipos: e31, e32, e33, e34, e41, e43, e44, e45, e46, e47
    """,
    'author': 'Tu Empresa',
    'website': 'https://tuempresa.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'l10n_do',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ecf_sequence_data.xml',
        'views/res_config_settings_view.xml',
        'views/ecf_certificate_view.xml',
        'views/account_move_view.xml',
        'wizard/dgii_ecf_wizard_view.xml',
    ],
    'external_dependencies': {
        'python': ['lxml', 'cryptography', 'requests', 'qrcode'],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
