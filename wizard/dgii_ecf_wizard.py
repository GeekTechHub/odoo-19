# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class DgiiEcfXmlWizard(models.TransientModel):
    """Wizard para visualizar el XML del e-CF."""
    _name = 'dgii.ecf.xml.wizard'
    _description = 'Visor XML e-CF'

    move_id = fields.Many2one('account.move', string='Factura', readonly=True)
    xml_content = fields.Text(string='XML e-CF', readonly=True)
    xml_type = fields.Selection(
        selection=[('unsigned', 'Sin Firmar'), ('signed', 'Firmado')],
        string='Tipo de XML',
        default='signed',
    )

    @api.onchange('xml_type')
    def _onchange_xml_type(self):
        if self.move_id:
            if self.xml_type == 'signed':
                self.xml_content = self.move_id.ecf_xml_signed or self.move_id.ecf_xml
            else:
                self.xml_content = self.move_id.ecf_xml

    def action_download_xml(self):
        """Descarga el XML como adjunto."""
        self.ensure_one()
        import base64
        xml = self.xml_content or ''
        attachment = self.env['ir.attachment'].create({
            'name': 'ecf_%s.xml' % (self.move_id.ref or self.move_id.name).replace('/', '_'),
            'type': 'binary',
            'datas': base64.b64encode(xml.encode('utf-8')),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'mimetype': 'application/xml',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'self',
        }
