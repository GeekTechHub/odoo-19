# -*- coding: utf-8 -*-
"""
Generador de XML e-CF según las especificaciones técnicas de la DGII
República Dominicana – Formato Comprobante Fiscal Electrónico v1.0
"""
import logging
from datetime import datetime
from lxml import etree

_logger = logging.getLogger(__name__)

# Namespace oficial de la DGII para e-CF
ECF_NAMESPACE = 'http://www.dgii.gov.do/eCF/2021-06-14/'
ECF_NS = {'ecf': ECF_NAMESPACE}


class ECFXmlGenerator:
    """Genera el XML del e-CF a partir de un account.move de Odoo."""

    def generate(self, move):

    if not move.ecf_type:
        raise ValueError("La factura no tiene definido el tipo de e-CF (ecf_type).")

    root = etree.Element(
        '{%s}ECF' % ECF_NAMESPACE,
        nsmap={None: ECF_NAMESPACE},
    )
        """
        Genera el XML completo del e-CF.

        :param move: account.move de Odoo
        :return: str – XML del e-CF sin firmar
        """
        root = etree.Element(
            '{%s}ECF' % ECF_NAMESPACE,
            nsmap={None: ECF_NAMESPACE},
        )

        self._add_encabezado(root, move)
        self._add_emisor(root, move)
        self._add_comprador(root, move)
        self._add_detalles(root, move)
        self._add_resumen(root, move)

        # Referenciado solo aplica para notas de crédito/débito
        if move.ecf_type in ('e33', 'e34') and move.reversed_entry_id:
            self._add_referencia(root, move)

        xml_bytes = etree.tostring(
    root,
    pretty_print=True,
    xml_declaration=True,
    encoding='UTF-8',
)

self._validate_xml(xml_bytes)

return xml_bytes.decode('utf-8')
    # ── Secciones del XML ────────────────────────────────────────────────────

    def _add_encabezado(self, parent, move):
        enc = etree.SubElement(parent, '{%s}Encabezado' % ECF_NAMESPACE)

        version = etree.SubElement(enc, 'Version')
        version.text = '1.0'

        # IdDoc
        id_doc = etree.SubElement(enc, 'IdDoc')
        self._tag(id_doc, 'TipoeCF', move.ecf_type or 'e32')
        self._tag(id_doc, 'eNCF', move.name or move.ref or '')
        self._tag(
            id_doc, 'FechaVencimientoSecuencia',
            move.invoice_date_due.strftime('%d-%m-%Y')
            if move.invoice_date_due else ''
        )
        self._tag(id_doc, 'IndicadorEnvioDiferido', '0')
        self._tag(id_doc, 'IndicadorMontoGravado', '0')

        tipo_ingreso = self._get_tipo_ingreso(move)
        self._tag(id_doc, 'TipoIngresos', tipo_ingreso)
        self._tag(id_doc, 'TipoPago', self._get_tipo_pago(move))
        self._tag(
            id_doc, 'FechaLimitePago',
            move.invoice_date_due.strftime('%d-%m-%Y')
            if move.invoice_date_due else ''
        )
        self._tag(id_doc, 'TotalPaginas', '1')

    def _add_emisor(self, parent, move):
        company = move.company_id
        partner = company.partner_id

        emisor = etree.SubElement(parent, 'Emisor')
        self._tag(emisor, 'RNCEmisor', (company.vat or '').replace('-', ''))
        self._tag(emisor, 'RazonSocialEmisor', company.name or '')
        self._tag(emisor, 'NombreComercialEmisor', company.ecf_trade_name or company.name or '')
        self._tag(emisor, 'Sucursal', '1')
        self._tag(emisor, 'DireccionEmisor', self._format_address(partner))
        self._tag(emisor, 'FechaEmision',
                  move.invoice_date.strftime('%d-%m-%Y') if move.invoice_date
                  else datetime.today().strftime('%d-%m-%Y'))
        self._tag(emisor, 'ActividadEconomica', company.ecf_business_activity or '000000')

    def _add_comprador(self, parent, move):
        partner = move.partner_id
        comprador = etree.SubElement(parent, 'Comprador')

        rnc = (partner.vat or '').replace('-', '')
        tipo_id = '1' if len(rnc) == 9 else ('2' if len(rnc) == 11 else '3')

        self._tag(comprador, 'TipoRNC', tipo_id)
        self._tag(comprador, 'RNCComprador', rnc)
        self._tag(comprador, 'RazonSocialComprador', partner.name or '')
        self._tag(comprador, 'DireccionComprador', self._format_address(partner))
        if partner.email:
            self._tag(comprador, 'CorreoElectronico', partner.email)

    def _add_detalles(self, parent, move):
        detalles = etree.SubElement(parent, 'Detalles')

        line_number = 1
        for line in move.invoice_line_ids.filtered(lambda l: not l.display_type):
            item = etree.SubElement(detalles, 'Item')

            self._tag(item, 'NumeroLinea', str(line_number))
            self._tag(item, 'TablaSubItems', '0')

            product = line.product_id
            self._tag(item, 'IndicadorBienoServicio',
                      '1' if product and product.type == 'service' else '2')
            self._tag(item, 'NombreItem', line.name or product.name or '')
            self._tag(item, 'IndicadorFacturacion', '1')
            self._tag(item, 'Cantidad', '%.2f' % line.quantity)
            self._tag(item, 'UnidadMedida', self._get_uom(line))
            self._tag(item, 'PrecioUnitarioItem', '%.2f' % line.price_unit)

            discount_pct = line.discount or 0.0
            if discount_pct:
                discount_amount = line.price_unit * line.quantity * discount_pct / 100.0
                self._tag(item, 'DescuentoMonto', '%.2f' % discount_amount)

            # ITBIS por línea
            itbis = self._get_line_tax(line)
            if itbis:
                self._tag(item, 'TablaImpuestosAdicionales', '1')
                imp_ad = etree.SubElement(item, 'ImpuestosAdicionales')
                impuesto = etree.SubElement(imp_ad, 'ImpuestoAdicional')
                self._tag(impuesto, 'TipoImpuesto', 'ITBIS')
                self._tag(impuesto, 'TasaImpuesto', '%.0f' % (itbis['rate'] * 100))
                self._tag(impuesto, 'MontoImpuesto', '%.2f' % itbis['amount'])

            self._tag(item, 'MontoItem', '%.2f' % line.price_subtotal)
            line_number += 1

    def _add_resumen(self, parent, move):
        resumen = etree.SubElement(parent, 'Resumen')

        subtotal = sum(
            l.price_subtotal for l in move.invoice_line_ids
            if not l.display_type
        )
        itbis_total = sum(
    line.price_total - line.price_subtotal
    for line in move.invoice_line_ids
    if not line.display_type
)

        self._tag(resumen, 'MontoGravadoTotal', '%.2f' % subtotal)
        self._tag(resumen, 'MontoGravadoI1', '%.2f' % subtotal)
        self._tag(resumen, 'MontoGravadoI2', '0.00')
        self._tag(resumen, 'MontoGravadoI3', '0.00')
        self._tag(resumen, 'MontoExento', '0.00')
        self._tag(resumen, 'ITBIS1', '%.2f' % itbis_total)
        self._tag(resumen, 'ITBIS2', '0.00')
        self._tag(resumen, 'ITBIS3', '0.00')
        self._tag(resumen, 'TotalITBIS', '%.2f' % itbis_total)
        self._tag(resumen, 'TotalImpuestosAdicionales', '0.00')
        self._tag(resumen, 'MontoTotal', '%.2f' % move.amount_total)
        self._tag(resumen, 'MontoNoFacturable', '0.00')
        self._tag(resumen, 'MontoPeriodo', '%.2f' % move.amount_total)
        self._tag(resumen, 'MontoAnticipo', '0.00')
        self._tag(resumen, 'MontoAPagar', '%.2f' % move.amount_total)

    def _add_referencia(self, parent, move):
        """Sección de referencia para notas de crédito/débito."""
        ref_move = move.reversed_entry_id
        ref_doc = etree.SubElement(parent, 'InformacionReferencia')
        # Referencia al e-CF original
        ref_doc = etree.SubElement(parent, 'InformacionReferencia')
        self._tag(ref_doc, 'ENCFModificado', ref_move.ref or '')
        self._tag(ref_doc, 'FechaENCFModificado',
                  ref_move.invoice_date.strftime('%d-%m-%Y')
                  if ref_move.invoice_date else '')
        self._tag(ref_doc, 'CodigoModificacion', '1')

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _tag(parent, name, text):
        el = etree.SubElement(parent, name)
        el.text = text or ''
        return el

    @staticmethod
    def _format_address(partner):
        parts = filter(None, [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name if partner.state_id else None,
        ])
        return ', '.join(parts) or 'N/A'

    @staticmethod
    def _get_tipo_ingreso(move):
        """01=Ingresos por Operaciones (default)."""
        return '01'

    @staticmethod
    def _get_tipo_pago(move):
        """
        Mapea el payment_term o journal a código DGII:
        1=Contado, 2=Crédito, 3=Mixto.
        """
        if move.invoice_payment_term_id:
            term = move.invoice_payment_term_id
            if term.line_ids and any(l.delay_type == 'days_after' and l.nb_days > 0
                                     for l in term.line_ids):
                return '2'
        return '1'

    @staticmethod
    def _get_uom(line):
        if line.product_uom_id:
        return 'UND'
            return line.product_uom_id.name[:3].upper()
        

    @staticmethod
    def _get_line_tax(line):
        for tax in line.tax_ids:
            if 'ITBIS' in (tax.name or '').upper():
                rate = abs(tax.amount) / 100.0
                amount = line.price_subtotal * rate
                return {'rate': rate, 'amount': amount}
        return None
