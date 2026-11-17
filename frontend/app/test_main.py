import unittest
from unittest.mock import Mock, patch

import requests

import main


INVOICE = {
    "numero_factura": "FAC-2025-001",
    "fecha_emision": "2025-08-15",
    "empresa": {
        "nombre": "Tech Solutions S.L.",
        "direccion": "Calle Mayor 123, Madrid",
        "telefono": "+34 912 345 678",
        "email": "contacto@example.es"
    },
    "cliente": {
        "nombre": "Industrias López",
        "direccion": "Av. Libertad 456, Barcelona",
        "telefono": "+34 933 456 789"
    },
    "detalle": [{
        "descripcion": "Servicios de consultoría",
        "cantidad": 2,
        "precio_unitario": 100.0,
        "total": 200.0
    }],
    "subtotal": 200.0,
    "impuesto": 42.0,
    "total": 242.0
}


class GeneratePdfTests(unittest.TestCase):
    def setUp(self):
        main.app.config['TESTING'] = True
        self.client = main.app.test_client()

    @patch('main.requests.get')
    def test_returns_inline_pdf(self, get):
        backend_response = Mock()
        backend_response.json.return_value = INVOICE
        get.return_value = backend_response

        response = self.client.post(
            '/generar-pdf',
            data={'id_factura': 'FAC-2025-001'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertTrue(response.headers['Content-Disposition'].startswith('inline;'))
        self.assertTrue(response.data.startswith(b'%PDF-'))
        get.assert_called_once_with(
            'http://backend:8000/facturas/v1/FAC-2025-001',
            timeout=(3, 10)
        )

    @patch('main.requests.get')
    def test_rejects_empty_invoice_id_without_calling_backend(self, get):
        response = self.client.post('/generar-pdf', data={'id_factura': ' '})

        self.assertEqual(response.status_code, 400)
        self.assertIn('Ingresa un número de factura', response.get_data(as_text=True))
        get.assert_not_called()

    @patch('main.requests.get', side_effect=requests.exceptions.Timeout)
    def test_reports_backend_timeout(self, get):
        response = self.client.post(
            '/generar-pdf',
            data={'id_factura': 'FAC-2025-001'}
        )

        self.assertEqual(response.status_code, 504)
        self.assertIn('tardó demasiado', response.get_data(as_text=True))

    @patch('main.requests.get', side_effect=requests.exceptions.ConnectionError)
    def test_reports_backend_connection_failure(self, get):
        response = self.client.post(
            '/generar-pdf',
            data={'id_factura': 'FAC-2025-001'}
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn('No se pudo conectar', response.get_data(as_text=True))

    @patch('main.requests.get')
    def test_rejects_invalid_backend_data(self, get):
        backend_response = Mock()
        backend_response.json.return_value = {"numero_factura": "FAC-2025-001"}
        get.return_value = backend_response

        response = self.client.post(
            '/generar-pdf',
            data={'id_factura': 'FAC-2025-001'}
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn('incompletos o inválidos', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
