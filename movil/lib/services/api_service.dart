import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

/// Servicio de comunicación con la API REST en el Subdominio HTTPS (/api/v1/...)
/// IAM-811 Machine Learning y Aprendizaje Profundo
/// Autor: Amilkar Hugo Guarachi Nina
class PeajeApiService {
  /// URL del subdominio en producción (configurable desde la pantalla de inicio de la app)
  String baseUrl = 'https://peaje.tudominio.com';
  String? sessionToken;
  Map<String, dynamic>? usuarioActual;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (sessionToken != null) 'Authorization': 'Bearer $sessionToken',
      };

  /// 1. POST /api/v1/auth/google — Valida token de Google Sign-In y Lista Blanca
  Future<Map<String, dynamic>> loginConGoogle({
    String? idToken,
    String? accessToken,
    required String emailGoogle,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1/auth/google');
    final resp = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'id_token': idToken ?? '',
        'access_token': accessToken ?? '',
        'email_google': emailGoogle,
      }),
    );

    final data = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
    if (resp.statusCode == 200 && data['ok'] == true) {
      sessionToken = data['token'];
      usuarioActual = data['usuario'];
    }
    data['statusCode'] = resp.statusCode;
    return data;
  }

  /// 2. POST /api/v1/pasos/frame — Envía un frame de video (2 a 5 fps) desde Modo Caseta
  Future<Map<String, dynamic>> enviarFrameCaseta({
    required Uint8List jpegBytes,
    int casetaId = 1,
  }) async {
    final uri = Uri.parse('$baseUrl/api/v1/pasos/frame');
    final b64 = 'data:image/jpeg;base64,${base64Encode(jpegBytes)}';

    final resp = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode({
        'imagen_base64': b64,
        'caseta_id': casetaId,
      }),
    );
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// 3. POST /api/v1/placas/consultar — Consulta una placa por texto en Modo Consulta
  Future<Map<String, dynamic>> consultarPlacaTexto(String placa) async {
    final uri = Uri.parse('$baseUrl/api/v1/placas/consultar');
    final resp = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode({'placa': placa}),
    );
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// 4. POST /api/v1/placas/consultar-imagen — Consulta una placa por foto (M1 + OCR) en Modo Consulta
  Future<Map<String, dynamic>> consultarPlacaImagen(Uint8List imageBytes) async {
    final uri = Uri.parse('$baseUrl/api/v1/placas/consultar-imagen');
    final b64 = 'data:image/jpeg;base64,${base64Encode(imageBytes)}';
    final resp = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode({'imagen_base64': b64}),
    );
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }

  /// 5. POST /api/v1/agente/chat — Envía mensaje al Agente Conversacional
  Future<Map<String, dynamic>> enviarMensajeAgente(String mensaje) async {
    final uri = Uri.parse('$baseUrl/api/v1/agente/chat');
    final resp = await http.post(
      uri,
      headers: _headers,
      body: jsonEncode({'mensaje': mensaje}),
    );
    return jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
  }
}
