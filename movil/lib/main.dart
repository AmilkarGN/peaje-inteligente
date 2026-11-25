import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:image_picker/image_picker.dart';
import 'services/api_service.dart';

List<CameraDescription> _cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    _cameras = await availableCameras();
  } catch (_) {
    _cameras = [];
  }
  runApp(const PeajeInteligenteApp());
}

class PeajeInteligenteApp extends StatelessWidget {
  const PeajeInteligenteApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Peaje Inteligente IAM-811',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF070B14),
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2563EB),
          brightness: Brightness.dark,
        ),
      ),
      home: const HomePeajeScreen(),
    );
  }
}

class HomePeajeScreen extends StatefulWidget {
  const HomePeajeScreen({super.key});

  @override
  State<HomePeajeScreen> createState() => _HomePeajeScreenState();
}

class _HomePeajeScreenState extends State<HomePeajeScreen> {
  final PeajeApiService _api = PeajeApiService();
  final GoogleSignIn _googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);
  final TextEditingController _urlCtrl =
      TextEditingController(text: 'https://peaje-inteligente.onrender.com');
  final TextEditingController _consultaTextoCtrl = TextEditingController();

  int _tabIndex = 0; // 0 = Modo Caseta, 1 = Modo Consulta
  int _casetaId = 1;
  double _fps = 2.0; // Captura automática de 2 a 5 fps (Sección 4.1)
  bool _capturaContinuaActiva = false;
  bool _procesandoFrame = false;
  String? _errorLogin;

  CameraController? _cameraController;
  Timer? _frameTimer;
  Map<String, dynamic>? _ultimoResultadoCaseta;

  final List<Map<String, dynamic>> _mensajesAgente = [];

  @override
  void initState() {
    super.initState();
    _inicializarCamara();
  }

  Future<void> _inicializarCamara() async {
    if (_cameras.isEmpty) return;
    final ctrl = CameraController(
      _cameras.first,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    try {
      await ctrl.initialize();
      if (mounted) {
        setState(() => _cameraController = ctrl);
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _frameTimer?.cancel();
    _cameraController?.dispose();
    _urlCtrl.dispose();
    _consultaTextoCtrl.dispose();
    super.dispose();
  }

  Future<void> _iniciarSesionConGoogleReal() async {
    setState(() => _errorLogin = null);
    _api.baseUrl = _urlCtrl.text.trim().replaceAll(RegExp(r'/$'), '');
    try {
      final account = await _googleSignIn.signIn();
      if (account == null) return;
      final auth = await account.authentication;
      final res = await _api.loginConGoogle(
        idToken: auth.idToken,
        accessToken: auth.accessToken,
        emailGoogle: account.email,
      );
      if (res['ok'] != true) {
        setState(() => _errorLogin = res['mensaje'] ?? 'Acceso denegado (403 Lista Blanca)');
      } else {
        setState(() {});
      }
    } catch (e) {
      setState(() => _errorLogin = 'Error al autenticar con Google: $e');
    }
  }

  Future<void> _iniciarSesionCuentaListaBlanca(String email) async {
    setState(() => _errorLogin = null);
    _api.baseUrl = _urlCtrl.text.trim().replaceAll(RegExp(r'/$'), '');
    try {
      final res = await _api.loginConGoogle(emailGoogle: email);
      if (res['ok'] != true) {
        setState(() => _errorLogin = res['mensaje'] ?? 'Acceso denegado (403)');
      } else {
        setState(() {});
      }
    } catch (e) {
      setState(() => _errorLogin = 'No se pudo conectar a ${_api.baseUrl}: $e');
    }
  }

  /// Activa o detiene el envío continuo de frames de video a la API (2 a 5 fps)
  void _toggleCapturaContinua() {
    if (_capturaContinuaActiva) {
      _frameTimer?.cancel();
      setState(() => _capturaContinuaActiva = false);
      return;
    }

    final intervalMs = (1000 / _fps).round();
    setState(() => _capturaContinuaActiva = true);
    _frameTimer = Timer.periodic(Duration(milliseconds: intervalMs), (_) {
      _capturarYEnviarFrame();
    });
  }

  Future<void> _capturarYEnviarFrame() async {
    if (_procesandoFrame || _cameraController == null || !_cameraController!.value.isInitialized) {
      return;
    }
    setState(() => _procesandoFrame = true);
    try {
      final xfile = await _cameraController!.takePicture();
      final bytes = await xfile.readAsBytes();
      final res = await _api.enviarFrameCaseta(
        jpegBytes: bytes,
        casetaId: _casetaId,
      );
      if (mounted) {
        setState(() => _ultimoResultadoCaseta = res);
      }
    } catch (_) {
    } finally {
      if (mounted) {
        setState(() => _procesandoFrame = false);
      }
    }
  }

  Future<void> _enviarTextoAlAgente(String texto) async {
    if (texto.trim().isEmpty) return;
    setState(() {
      _mensajesAgente.add({'rol': 'usuario', 'texto': texto});
    });
    _consultaTextoCtrl.clear();
    try {
      final res = await _api.consultarPlacaTexto(texto);
      setState(() {
        _mensajesAgente.add({
          'rol': 'agente',
          'texto': res['respuesta_agente'] ?? 'Sin respuesta',
          'estado': res['estado'],
        });
      });
    } catch (e) {
      setState(() {
        _mensajesAgente.add({'rol': 'agente', 'texto': 'Error de conexión: $e'});
      });
    }
  }

  Future<void> _enviarFotoPlacaAlAgente(ImageSource source) async {
    final picker = ImagePicker();
    final xfile = await picker.pickImage(source: source, imageQuality: 85);
    if (xfile == null) return;
    final bytes = await xfile.readAsBytes();
    setState(() {
      _mensajesAgente.add({
        'rol': 'usuario',
        'texto': '📷 Foto de placa enviada para lectura M1 + OCR',
        'bytes': bytes,
      });
    });
    try {
      final res = await _api.consultarPlacaImagen(bytes);
      setState(() {
        _mensajesAgente.add({
          'rol': 'agente',
          'texto': res['respuesta_agente'] ?? 'Sin respuesta',
          'estado': res['estado'],
        });
      });
    } catch (e) {
      setState(() {
        _mensajesAgente.add({'rol': 'agente', 'texto': 'Error al procesar imagen: $e'});
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_api.usuarioActual == null) {
      return _buildLoginScreen();
    }
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF0F172A),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('🛣️ Peaje Inteligente IAM-811', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            Text(
              '${_api.usuarioActual!['email_google']} · ROL: ${_api.usuarioActual!['rol'].toString().toUpperCase()}',
              style: const TextStyle(fontSize: 11, color: Colors.blueAccent),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.redAccent),
            onPressed: () {
              _frameTimer?.cancel();
              setState(() {
                _capturaContinuaActiva = false;
                _api.sessionToken = null;
                _api.usuarioActual = null;
              });
            },
          )
        ],
      ),
      body: _tabIndex == 0 ? _buildModoCaseta() : _buildModoConsulta(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (idx) => setState(() => _tabIndex = idx),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.videocam), label: 'Modo Caseta (2-5 fps)'),
          NavigationDestination(icon: Icon(Icons.smart_toy), label: 'Modo Consulta (Agente)'),
        ],
      ),
    );
  }

  Widget _buildLoginScreen() {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: const Color(0xFF111827),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: const Color(0xFF1E293B)),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.toll, size: 54, color: Colors.blueAccent),
                const SizedBox(height: 12),
                const Text(
                  'Control Inteligente de Peaje',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
                const Text(
                  'IAM-811 · Amilkar Hugo Guarachi Nina',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 18),
                TextField(
                  controller: _urlCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Subdominio HTTPS del Backend Web',
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.cloud),
                  ),
                ),
                const SizedBox(height: 16),
                if (_errorLogin != null)
                  Container(
                    padding: const EdgeInsets.all(12),
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: Colors.red.shade900.withOpacity(0.5),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.redAccent),
                    ),
                    child: Text(
                      '⛔ $_errorLogin',
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.login),
                    label: const Text('Iniciar Sesión con Google Sign-In'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.blueAccent,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    onPressed: _iniciarSesionConGoogleReal,
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () => _iniciarSesionCuentaListaBlanca('guamilkar@gmail.com'),
                    child: const Text('Google Auth: guamilkar@gmail.com (Admin)'),
                  ),
                ),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    onPressed: () => _iniciarSesionCuentaListaBlanca('doc.alvaro.pinto.ma@unifranz.edu.bo'),
                    child: const Text('Google Auth: doc.alvaro.pinto.ma@unifranz.edu.bo'),
                  ),
                ),
                SizedBox(
                  width: double.infinity,
                  child: TextButton(
                    onPressed: () => _iniciarSesionCuentaListaBlanca('no.autorizado@gmail.com'),
                    child: const Text(
                      '🚫 Probar Cuenta No Autorizada (Rechazo 403)',
                      style: TextStyle(color: Colors.redAccent, fontSize: 12),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildModoCaseta() {
    final res = _ultimoResultadoCaseta;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Selector de Caseta y Slider de FPS (2 a 5 fps)
        Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFF111827),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Caseta Activa:', style: TextStyle(fontWeight: FontWeight.bold)),
                  DropdownButton<int>(
                    value: _casetaId,
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('Caseta Central #1')),
                      DropdownMenuItem(value: 2, child: Text('Caseta Achica Arriba #2')),
                      DropdownMenuItem(value: 3, child: Text('Caseta Urujara #3')),
                    ],
                    onChanged: (v) => setState(() => _casetaId = v ?? 1),
                  ),
                ],
              ),
              Row(
                children: [
                  Text('Frecuencia Video: ${_fps.toStringAsFixed(1)} FPS'),
                  Expanded(
                    child: Slider(
                      value: _fps,
                      min: 2.0,
                      max: 5.0,
                      divisions: 6,
                      label: '${_fps.toStringAsFixed(1)} fps',
                      onChanged: (v) => setState(() => _fps = v),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),

        // Vista previa de Cámara en Vivo
        Container(
          height: 250,
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: _capturaContinuaActiva ? Colors.greenAccent : Colors.blueGrey,
              width: 2,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: _cameraController != null && _cameraController!.value.isInitialized
              ? CameraPreview(_cameraController!)
              : const Center(
                  child: Text('Cámara lista para capturar frames hacia /api/v1/pasos/frame'),
                ),
        ),
        const SizedBox(height: 12),

        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                icon: Icon(_capturaContinuaActiva ? Icons.stop : Icons.videocam),
                label: Text(_capturaContinuaActiva
                    ? 'Detener Stream (${_fps.toStringAsFixed(0)} FPS)'
                    : 'Iniciar Captura Video (${_fps.toStringAsFixed(0)} FPS)'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: _capturaContinuaActiva ? Colors.redAccent : Colors.green.shade700,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
                onPressed: _toggleCapturaContinua,
              ),
            ),
            const SizedBox(width: 8),
            ElevatedButton.icon(
              icon: const Icon(Icons.camera_alt),
              label: const Text('Capturar 1 Frame'),
              onPressed: _capturarYEnviarFrame,
            ),
          ],
        ),
        const SizedBox(height: 16),

        // Resultado de la Inferencia devuelto por la API (Placa, Categoría, Ejes, Pasajeros, Tarifa y Estado)
        if (res != null)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF111827),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: res['estado'] == 'AUTORIZADO' ? Colors.greenAccent : Colors.redAccent,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'PLACA: ${res['placa'] ?? 'ILEGIBLE'}',
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                    ),
                    Chip(
                      label: Text('${res['estado']}'),
                      backgroundColor: res['estado'] == 'AUTORIZADO'
                          ? Colors.green.shade800
                          : Colors.red.shade900,
                    ),
                  ],
                ),
                const Divider(),
                Text('• Categoría (M2 YOLO-seg): ${res['categoria'].toString().toUpperCase()}'),
                Text('• Número de Ejes (M3 YOLO-pose): ${res['ejes']} ejes'),
                Text('• Pasajeros Detectados (Bono M4): ${res['pasajeros']} ocupante(s)'),
                Text(
                  '• Tarifa Cobrada: Bs ${res['tarifa']}',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.greenAccent,
                  ),
                ),
                Text('• Latencia en la Nube: ${res['latencia']} ms',
                    style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildModoConsulta() {
    return Column(
      children: [
        // Botones rápidos de los 4 estados para pruebas en móvil
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              ActionChip(
                label: const Text('1. Con paso (29B110559)'),
                onPressed: () => _enviarTextoAlAgente('29B110559'),
              ),
              const SizedBox(width: 6),
              ActionChip(
                label: const Text('2. Sin paso (59M-181859)'),
                onPressed: () => _enviarTextoAlAgente('59M-181859'),
              ),
              const SizedBox(width: 6),
              ActionChip(
                label: const Text('3. No registrada (EVASOR-901)'),
                onPressed: () => _enviarTextoAlAgente('EVASOR-901'),
              ),
              const SizedBox(width: 6),
              ActionChip(
                label: const Text('4. Error OCR (298110559)'),
                onPressed: () => _enviarTextoAlAgente('298110559'),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(14),
            itemCount: _mensajesAgente.length,
            itemBuilder: (ctx, i) {
              final m = _mensajesAgente[i];
              final esUser = m['rol'] == 'usuario';
              return Align(
                alignment: esUser ? Alignment.centerRight : Alignment.centerLeft,
                child: Container(
                  margin: const EdgeInsets.symmetric(vertical: 5),
                  padding: const EdgeInsets.all(12),
                  constraints: const BoxConstraints(maxWidth: 320),
                  decoration: BoxDecoration(
                    color: esUser ? Colors.blueAccent : const Color(0xFF1E293B),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (m['bytes'] != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Image.memory(m['bytes'] as Uint8List, height: 110),
                        ),
                      Text(m['texto'].toString(), style: const TextStyle(fontSize: 13)),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.all(10),
          color: const Color(0xFF0F172A),
          child: Row(
            children: [
              IconButton(
                icon: const Icon(Icons.camera_alt, color: Colors.cyanAccent),
                tooltip: 'Tomar foto de placa',
                onPressed: () => _enviarFotoPlacaAlAgente(ImageSource.camera),
              ),
              IconButton(
                icon: const Icon(Icons.photo_library, color: Colors.amberAccent),
                tooltip: 'Elegir foto de galería',
                onPressed: () => _enviarFotoPlacaAlAgente(ImageSource.gallery),
              ),
              Expanded(
                child: TextField(
                  controller: _consultaTextoCtrl,
                  decoration: const InputDecoration(
                    hintText: 'Escribir placa (ej. 29B110559)...',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  onSubmitted: _enviarTextoAlAgente,
                ),
              ),
              const SizedBox(width: 6),
              IconButton(
                icon: const Icon(Icons.send, color: Colors.blueAccent),
                onPressed: () => _enviarTextoAlAgente(_consultaTextoCtrl.text),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
