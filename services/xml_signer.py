# -*- coding: utf-8 -*-
"""
Firma digital de XML e-CF mediante XMLDSig (RSA-SHA256).
Utiliza la librería cryptography y lxml para cumplir con las
especificaciones de firma de la DGII.
"""
import base64
import hashlib
import logging
from datetime import datetime, timezone

from lxml import etree
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_der_x509_certificate

_logger = logging.getLogger(__name__)

# Namespaces XMLDSig
DS_NS = 'http://www.w3.org/2000/09/xmldsig#'
ECF_NS = 'http://www.dgii.gov.do/eCF/2021-06-14/'


class ECFXmlSigner:
    """Firma un XML e-CF con un certificado PKCS#12 (.p12)."""

    def sign(self, xml_content: str, cert_bytes: bytes, password: str) -> str:
        """
        Firma el XML del e-CF.

        :param xml_content:  XML sin firmar (str)
        :param cert_bytes:   Contenido binario del .p12
        :param password:     Contraseña del .p12
        :return:             XML firmado (str)
        """
        password_bytes = password.encode('utf-8') if password else None

        # Cargar certificado y clave privada
        private_key, certificate, additional_certs = load_key_and_certificates(
            cert_bytes, password_bytes
        )

        # Parsear XML
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.fromstring(xml_content.encode('utf-8'), parser)

        # Canonicalizar el contenido a firmar (C14N)
        c14n_bytes = self._canonicalize(root)

        # Calcular DigestValue (SHA-256) del documento
        digest = hashlib.sha256(c14n_bytes).digest()
        digest_b64 = base64.b64encode(digest).decode('ascii')

        # Construir SignedInfo
        signed_info_xml = self._build_signed_info(digest_b64, root)
        signed_info_c14n = self._canonicalize_element(signed_info_xml)

        # Firmar con RSA-SHA256
        signature_bytes = private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        signature_b64 = base64.b64encode(signature_bytes).decode('ascii')

        # Serializar certificado en base64
        cert_der = certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode('ascii')

        # Construir nodo Signature completo
        signature_node = self._build_signature_node(
            signed_info_xml,
            signature_b64,
            cert_b64,
            certificate,
        )

        # Adjuntar firma al XML
        root.append(signature_node)

        # Agregar FechaHoraFirma si no existe
        self._add_sign_timestamp(root)

        signed_xml = etree.tostring(
            root,
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8',
        )
        return signed_xml.decode('utf-8')

    # ── Construcción de nodos XMLDSig ─────────────────────────────────────────

    def _build_signed_info(self, digest_b64: str, root) -> etree._Element:
        """Construye el elemento <SignedInfo>."""
        si = etree.Element('{%s}SignedInfo' % DS_NS, nsmap={'ds': DS_NS})

        cm = etree.SubElement(si, '{%s}CanonicalizationMethod' % DS_NS)
        cm.set('Algorithm', 'http://www.w3.org/TR/2001/REC-xml-c14n-20010315')

        sm = etree.SubElement(si, '{%s}SignatureMethod' % DS_NS)
        sm.set('Algorithm', 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256')

        ref = etree.SubElement(si, '{%s}Reference' % DS_NS)
        ref.set('URI', '')

        transforms = etree.SubElement(ref, '{%s}Transforms' % DS_NS)
        t = etree.SubElement(transforms, '{%s}Transform' % DS_NS)
        t.set('Algorithm', 'http://www.w3.org/2000/09/xmldsig#enveloped-signature')

        dm = etree.SubElement(ref, '{%s}DigestMethod' % DS_NS)
        dm.set('Algorithm', 'http://www.w3.org/2001/04/xmlenc#sha256')

        dv = etree.SubElement(ref, '{%s}DigestValue' % DS_NS)
        dv.text = digest_b64

        return si

    def _build_signature_node(
        self,
        signed_info: etree._Element,
        signature_b64: str,
        cert_b64: str,
        certificate,
    ) -> etree._Element:
        """Construye el nodo <Signature> completo para adjuntar al XML."""
        sig = etree.Element('{%s}Signature' % DS_NS, nsmap={'ds': DS_NS})
        sig.append(signed_info)

        sv = etree.SubElement(sig, '{%s}SignatureValue' % DS_NS)
        sv.text = signature_b64

        key_info = etree.SubElement(sig, '{%s}KeyInfo' % DS_NS)
        x509_data = etree.SubElement(key_info, '{%s}X509Data' % DS_NS)
        x509_cert = etree.SubElement(x509_data, '{%s}X509Certificate' % DS_NS)
        x509_cert.text = cert_b64

        # Subject name
        subject = etree.SubElement(x509_data, '{%s}X509SubjectName' % DS_NS)
        subject.text = certificate.subject.rfc4514_string()

        return sig

    # ── Utilidades de canonicalización ────────────────────────────────────────

    @staticmethod
    def _canonicalize(root: etree._Element) -> bytes:
        """C14N (Canonical XML) del elemento."""
        from io import BytesIO
        buf = BytesIO()
        root.getroottree().write_c14n(buf)
        return buf.getvalue()

    @staticmethod
    def _canonicalize_element(element: etree._Element) -> bytes:
        """C14N de un elemento individual."""
        from io import BytesIO
        tree = etree.ElementTree(element)
        buf = BytesIO()
        tree.write_c14n(buf)
        return buf.getvalue()

    @staticmethod
    def _add_sign_timestamp(root: etree._Element):
        """
        Agrega o actualiza el elemento <FechaHoraFirma> con la hora actual UTC.
        Si ya existe, lo actualiza; si no, lo inserta antes de la firma.
        """
        ns = ECF_NS
        tag = '{%s}FechaHoraFirma' % ns if ns else 'FechaHoraFirma'

        # Buscar existente
        existing = root.find(tag)
        if existing is None:
            existing = root.find('FechaHoraFirma')

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

        if existing is not None:
            existing.text = now_str
        else:
            ts = etree.Element('FechaHoraFirma')
            ts.text = now_str
            # Insertar antes del nodo Signature si existe
            sig_tag = '{%s}Signature' % DS_NS
            sig_node = root.find(sig_tag)
            if sig_node is not None:
                idx = list(root).index(sig_node)
                root.insert(idx, ts)
            else:
                root.append(ts)
